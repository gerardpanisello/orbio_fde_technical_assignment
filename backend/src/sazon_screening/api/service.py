"""Turn orchestration (FR-2, FR-4, FR-14): load state -> agent -> save, one turn at a time.

Every write the API makes goes through here. Reads for the dashboard are plain repo
queries in the routes. The agent decides nothing about storage and never raises for an
LLM problem (spec 003 FR-4); this layer adds the lock, the transaction and the clock.

No database session is held while the agent runs: a turn can take seconds of LLM time.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from sazon_screening.api import repo
from sazon_screening.api.db import Sessions
from sazon_screening.api.models import Conversation, Message, RecruiterAction, SummaryRow
from sazon_screening.api.slots import SlotProvider
from sazon_screening.api.staffing import Staffing, area_of_row, area_of_state, load_staffing
from sazon_screening.api.staffing import seed_staffing as insert_seed
from sazon_screening.config import EngineConfig, ZoneStaffingConfig
from sazon_screening.engine import CandidateRecord, ConversationState, build_record
from sazon_screening.llm.extraction.extractor import InboundMessage, TranscriptEntry
from sazon_screening.llm.pipeline import Event, ScreeningAgent
from sazon_screening.llm.summary.summarizer import Summary
from sazon_screening.llm.trace import TurnContextIn, TurnResult
from sazon_screening.vocab import Country, Language, Status

logger = logging.getLogger("sazon_screening.api")
Clock = Callable[[], datetime]
ActionName = Literal["shortlist", "reject", "hire", "override", "note"]

# FR-9: what each recruiter action does to `recruiter_status` (a note changes nothing).
RECRUITER_STATUS: dict[ActionName, str] = {
    "shortlist": "shortlisted",
    "reject": "rejected",
    "hire": "hired",
    "override": "shortlisted",
}
OVERRIDABLE = frozenset({Status.disqualified, Status.needs_review})


def utc_now() -> datetime:
    return datetime.now(UTC)


class ConversationNotFound(Exception):  # noqa: N818 - reads as the condition -> 404
    pass


class NotAllowed(Exception):  # noqa: N818 - the request is valid but not now -> 409
    pass


@dataclass(frozen=True)
class TurnOutcome:
    result: TurnResult
    status: Status


class ScreeningService:
    def __init__(
        self,
        agent: ScreeningAgent,
        sessions: Sessions,
        slots: SlotProvider,
        clock: Clock = utc_now,
        staffing_seed: ZoneStaffingConfig | None = None,
    ) -> None:
        self._agent = agent
        self._sessions = sessions
        self._slots = slots
        self._clock = clock
        self._staffing_seed = staffing_seed  # spec 015: written to an empty table at startup
        # FR-4: one turn at a time per conversation. Per process: enough for one instance
        # (several instances need a DB row lock or a queue; deployment design, 014).
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def now(self) -> datetime:
        return self._clock()

    def with_agent(self, agent: ScreeningAgent) -> "ScreeningService":
        """The same database, slots and clock behind another agent (the offline demo seed)."""
        return ScreeningService(
            agent, self._sessions, self._slots, self._clock, self._staffing_seed
        )

    async def init_zone_staffing(self) -> bool:
        """Seed `zone_staffing` from config if the table is empty (spec 015 FR-1).

        Idempotent: after the first start the database is the source of truth, so edits
        made in the dashboard are never overwritten by the YAML. True if it inserted.
        """
        if self._staffing_seed is None:
            return False
        async with self._sessions.begin() as session:
            return await insert_seed(session, self._staffing_seed, self._clock())

    # --- candidate side ------------------------------------------------------------------

    async def start_conversation(
        self,
        language: Language = Language.es,
        country_hint: Country | None = None,
        *,
        conversation_id: str | None = None,
        at: datetime | None = None,
    ) -> str:
        """FR-1: store a new conversation with Sofi's greeting; returns its id."""
        now = at or self._clock()
        conversation_id = conversation_id or str(uuid4())
        context = self._context(country_hint, now)
        result = await self._agent.start_conversation(
            language=language, context=context, conversation_id=conversation_id
        )
        async with self._sessions.begin() as session:
            conversation = Conversation(id=conversation_id, created_at=now, recruiter_status="new")
            self._copy_state(conversation, result.state, now)
            repo.add(session, conversation)
            self._add_messages(session, conversation_id, None, result, now)
        return conversation_id

    async def send_message(
        self, conversation_id: str, text: str, *, at: datetime | None = None
    ) -> TurnOutcome:
        """FR-2: one candidate turn. A closed conversation still answers (the engine acks)."""
        async with self._locks[conversation_id]:
            now = at or self._clock()
            state, history = await self._load(conversation_id)
            zone_full = await self._zone_full(state, conversation_id)
            result = await self._agent.handle_message(
                state,
                InboundMessage(text=text),
                history,
                today=now.date(),
                context=self._context(state.country_hint, now, zone_full=zone_full),
                conversation_id=conversation_id,
            )
            return await self._save_turn(conversation_id, text, result, now)

    async def send_event(
        self, conversation_id: str, event: Event, *, at: datetime | None = None
    ) -> TurnOutcome:
        """FR-13: timer and calendar events (silence_expired until 008 adds timers)."""
        async with self._locks[conversation_id]:
            now = at or self._clock()
            state, _ = await self._load(conversation_id)
            zone_full = await self._zone_full(state, conversation_id)
            result = await self._agent.handle_event(
                state,
                event,
                today=now.date(),
                context=self._context(state.country_hint, now, zone_full=zone_full),
                conversation_id=conversation_id,
            )
            return await self._save_turn(conversation_id, None, result, now)

    # --- summaries (FR-8, FR-14) ---------------------------------------------------------

    @property
    def engine_config(self) -> EngineConfig:
        return self._agent.engine_config

    @property
    def default_summary_language(self) -> Language:
        return self._agent.default_summary_language

    async def write_summary(self, conversation_id: str, *, at: datetime | None = None) -> None:
        """Background task after a reply (FR-14): never raises, logs with the conversation id."""
        try:
            await self._generate_summary(conversation_id, self.default_summary_language, at=at)
        except Exception:
            logger.exception("summary failed (conversation %s)", conversation_id)

    async def summary(self, conversation_id: str, language: Language) -> SummaryRow:
        """FR-8: the stored summary in `language`, generated and stored once if missing."""
        async with self._sessions() as session:
            stored = await repo.get_summary(session, conversation_id, language.value)
            conversation = await repo.get_conversation(session, conversation_id)
        if stored is not None:
            return stored
        if conversation is None:
            raise ConversationNotFound(conversation_id)
        if conversation.status == Status.in_progress:
            raise NotAllowed("there is no summary until the conversation ends")
        return await self._generate_summary(conversation_id, language)

    async def _generate_summary(
        self, conversation_id: str, language: Language, *, at: datetime | None = None
    ) -> SummaryRow:
        async with self._sessions() as session:
            conversation = await self._get(session, conversation_id)
            messages = await repo.list_messages(session, conversation_id)
        record = CandidateRecord.model_validate(conversation.record_json)
        transcript = [_entry(m) for m in messages]
        summary, calls = await self._agent.summarise(
            record, transcript, language, conversation_id=conversation_id
        )
        row = SummaryRow(
            conversation_id=conversation_id,
            language=language.value,
            json=summary.model_dump(mode="json"),
            created_at=at or self._clock(),
            cost_usd=sum(call.cost_usd for call in calls),
        )
        async with self._sessions.begin() as session:
            current = await self._get(session, conversation_id)
            if current.status == summary.status:  # else a newer turn made it stale: drop it
                await repo.save_summary(session, row)
        return row

    # --- recruiter side (FR-9) -----------------------------------------------------------

    async def record_action(
        self, conversation_id: str, action: ActionName, note: str | None
    ) -> RecruiterAction:
        async with self._sessions.begin() as session:
            conversation = await self._get(session, conversation_id)
            status = Status(conversation.status)
            if action == "override" and status not in OVERRIDABLE:
                raise NotAllowed("override is only for disqualified or needs_review candidates")
            if status is Status.opted_out and action in ("shortlist", "hire", "override"):
                raise NotAllowed("the candidate opted out: do not contact")
            if action == "hire" and not await repo.has_action(session, conversation_id, "hire"):
                await self._add_hired_driver(session, conversation)
            if action in RECRUITER_STATUS:
                conversation.recruiter_status = RECRUITER_STATUS[action]
            if action == "override":
                conversation.recruiter_override = True  # the agent's outcome stays for audit
            row = RecruiterAction(
                conversation_id=conversation_id, action=action, note=note, created_at=self._clock()
            )
            repo.add(session, row)
        return row

    # --- helpers -------------------------------------------------------------------------

    async def _add_hired_driver(self, session: AsyncSession, conversation: Conversation) -> None:
        """FR-5: the first "hire" of a candidate adds one driver to their area, once.

        A second "hire" of the same candidate changes nothing (the caller checks the action
        history); undoing a hire is a manual edit on the "Zonas" page. An area without
        staffing data stays without data.
        """
        area_id = area_of_row(conversation)
        row = await repo.get_staffing(session, area_id) if area_id else None
        if row is None:
            logger.info("hire without staffing data (conversation %s)", conversation.id)
            return
        row.current_drivers += 1
        row.updated_at = self._clock()

    async def _zone_full(self, state: ConversationState, conversation_id: str) -> bool:
        """Spec 015 FR-4: is the candidate's area at or above target right now?

        Sent on every turn; the engine only reads it when the recap is confirmed. A
        staffing read that fails must not break the conversation: slots are offered as before.
        """
        area_id = area_of_state(state)
        if area_id is None:
            return False
        try:
            async with self._sessions() as session:
                row = await repo.get_staffing(session, area_id)
            return Staffing({area_id: row} if row else {}).is_full(area_id)
        except Exception:
            logger.exception("staffing lookup failed (conversation %s)", conversation_id)
            return False

    def _context(
        self, country_hint: Country | None, now: datetime, *, zone_full: bool = False
    ) -> TurnContextIn:
        return TurnContextIn(
            country_hint=country_hint, slots=self._slots.slots(now.date()), zone_full=zone_full
        )

    async def _load(self, conversation_id: str) -> tuple[ConversationState, list[TranscriptEntry]]:
        async with self._sessions() as session:
            conversation = await self._get(session, conversation_id)
            messages = await repo.list_messages(session, conversation_id)
        state = ConversationState.model_validate(conversation.state_json)
        return state, [_entry(m) for m in messages]

    async def _save_turn(
        self, conversation_id: str, text: str | None, result: TurnResult, now: datetime
    ) -> TurnOutcome:
        async with self._sessions.begin() as session:
            conversation = await self._get(session, conversation_id)
            previous = conversation.status
            self._add_messages(session, conversation_id, text, result, now)
            staffing = await load_staffing(session)
            self._copy_state(conversation, result.state, now, staffing)
            if conversation.status != previous:
                await repo.delete_summaries(session, conversation_id)  # they describe the past
            if result.state.status is Status.opted_out:
                await repo.redact_messages(session, conversation_id)  # 002 FR-11
        if result.state.last_error:
            logger.error(
                "engine error %s (conversation %s)", result.state.last_error, conversation_id
            )
        return TurnOutcome(result=result, status=result.state.status)

    def _add_messages(
        self,
        session: AsyncSession,
        conversation_id: str,
        text: str | None,
        result: TurnResult,
        now: datetime,
    ) -> None:
        """The candidate's message, then the reply. The trace goes on the reply, or on the
        candidate's message when nothing is sent back."""
        trace = result.trace
        numbers = {
            "trace_json": trace.model_dump(mode="json"),
            "cost_usd": trace.cost_usd,
            "latency_ms": trace.latency_ms,
            "fallback": trace.phrasing.outcome == "fallback",
        }
        reply = result.reply
        if text is not None:
            extra = numbers if reply is None else {}
            repo.add(
                session,
                Message(
                    conversation_id=conversation_id,
                    role="candidate",
                    text=text,
                    created_at=now,
                    **extra,
                ),
            )
        if reply is not None:
            quick_replies = [q.model_dump() for q in reply.quick_replies]
            repo.add(
                session,
                Message(
                    conversation_id=conversation_id,
                    role="agent",
                    text=reply.text,
                    quick_replies_json=quick_replies,
                    created_at=now,
                    **numbers,
                ),
            )

    def _copy_state(
        self,
        row: Conversation,
        state: ConversationState,
        now: datetime,
        staffing: Staffing | None = None,
    ) -> None:
        """Store the state and record, and copy the columns the dashboard filters on.

        The record's score uses the area's occupancy at this moment: it is the score at
        close, kept for audit; the dashboard shows a live one (spec 015 FR-6).
        """
        occupancy = staffing.ratio(area_of_state(state)) if staffing else None
        record = build_record(state, self._agent.engine_config, occupancy=occupancy)
        location = state.profile.location.value
        row.updated_at = now
        row.status = state.status.value
        row.stage = state.stage.value
        row.language = state.language.value
        row.country = (location.country if location else None) or state.country_hint
        row.city = location.city if location else None
        row.zone = location.zone if location else None
        row.full_name = state.profile.full_name.value
        row.score = record.score.score if record.score else None
        row.bucket = record.score.bucket.value if record.score else None
        row.disqualification_reason = record.disqualification_reason
        row.drop_off_stage = record.drop_off_stage
        row.interview_slot = record.selected_slot_id
        row.state_json = state.model_dump(mode="json")
        row.record_json = record.model_dump(mode="json")
        row.flags_json = [flag.value for flag in record.flags]

    async def _get(self, session: AsyncSession, conversation_id: str) -> Conversation:
        conversation = await repo.get_conversation(session, conversation_id)
        if conversation is None:
            raise ConversationNotFound(conversation_id)
        return conversation


def _entry(message: Message) -> TranscriptEntry:
    return TranscriptEntry(
        role="candidate" if message.role == "candidate" else "agent", text=message.text
    )


def summary_of(row: SummaryRow) -> Summary:
    return Summary.model_validate(row.json)
