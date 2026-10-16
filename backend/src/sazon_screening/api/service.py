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
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from sazon_screening.api import repo
from sazon_screening.api.bookings import SlotUnavailable, sync_booking
from sazon_screening.api.db import Sessions
from sazon_screening.api.models import (
    SEAT_HOLDING,
    Conversation,
    InboundSeen,
    InterviewBooking,
    Message,
    RecruiterAction,
    SummaryRow,
)
from sazon_screening.api.slots import SlotProvider
from sazon_screening.api.staffing import Staffing, area_of_row, area_of_state, load_staffing
from sazon_screening.api.staffing import seed_staffing as insert_seed
from sazon_screening.config import EngineConfig, ZoneStaffingConfig
from sazon_screening.engine import (
    CandidateRecord,
    ConversationState,
    SilenceExpired,
    SlotTaken,
    build_record,
    register_for,
)
from sazon_screening.llm.extraction.extractor import InboundMessage, TranscriptEntry
from sazon_screening.llm.phrasing.phraser import OutboundMessage
from sazon_screening.llm.pipeline import Event, ScreeningAgent
from sazon_screening.llm.slots import SlotDisplay
from sazon_screening.llm.summary.summarizer import Summary
from sazon_screening.llm.trace import TurnContextIn, TurnResult
from sazon_screening.reengagement import (
    Abandon,
    Planned,
    ReengagementConfig,
    Silence,
    next_step,
    timezone_for,
)
from sazon_screening.scheduling.ics import CalendarEvent, build_ics
from sazon_screening.scheduling.reminder import reminder_due
from sazon_screening.vocab import Country, Language, Status
from sazon_screening.whatsapp.phone import phone_hash, phone_ref

logger = logging.getLogger("sazon_screening.api")
Clock = Callable[[], datetime]
# Spec 010 AC-2: a booking that lost a race for a seat (unique index) is retried this many
# times in all, re-counting the seats each time; a short pause lets the winner commit.
BOOKING_ATTEMPTS = 3
BOOKING_BACKOFF_S = 0.05
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


class BookingNotFound(Exception):  # noqa: N818 - reads as the condition -> 404
    pass


AttendanceStatus = Literal["attended", "no_show", "booked"]


@dataclass(frozen=True)
class TurnOutcome:
    result: TurnResult
    status: Status


SkipReason = Literal["disabled", "closed", "candidate_last", "not_due", "already_sent"]


@dataclass(frozen=True)
class Reengaged:
    """What one re-engagement step did (spec 008): a reminder, the abandon, or nothing."""

    action: Literal["follow_up", "abandon", "none"]
    status: Status
    step: int | None = None  # the reminder sent (follow_up)
    reply: OutboundMessage | None = None  # the reminder, or the engine's close (abandon)
    requires_template: bool = False
    summary_due: bool = False  # abandon closed the conversation: write the summary
    reason: SkipReason | None = None  # why nothing was done
    planned: Planned | None = None  # the next step, when it is not due yet


Channel = Literal["web", "whatsapp"]
DeliveryKind = Literal["reply", "follow_up", "close", "reminder"]  # reminder: spec 010


@dataclass(frozen=True)
class Outbound:
    """A message for a channel that pushes (spec 016): the web chat pulls instead."""

    conversation_id: str
    phone: str | None
    reply: OutboundMessage
    kind: DeliveryKind
    # Later than the WhatsApp window after the candidate's last message: free text would
    # be rejected, only an approved template can go (spec 008 FR-3).
    outside_window: bool = False


class Delivery(Protocol):
    """A channel adapter's outbound side. Must not raise: it logs and carries on."""

    async def deliver(self, outbound: Outbound) -> None: ...


class ScreeningService:
    def __init__(
        self,
        agent: ScreeningAgent,
        sessions: Sessions,
        slots: SlotProvider,
        clock: Clock = utc_now,
        staffing_seed: ZoneStaffingConfig | None = None,
        reengagement: ReengagementConfig | None = None,
        public_base_url: str | None = None,
    ) -> None:
        self._agent = agent
        self._sessions = sessions
        self._slots = slots
        self._clock = clock
        self._staffing_seed = staffing_seed  # spec 015: written to an empty table at startup
        self._reengagement = reengagement  # spec 008, already time-scaled; None: no reminders
        # Spec 010 FR-5: where candidates can reach the API (the .ics link on WhatsApp).
        self._public_base_url = public_base_url.rstrip("/") if public_base_url else None
        # FR-4: one turn at a time per conversation. Per process: enough for one instance
        # (several instances need a DB row lock or a queue; deployment design, 014).
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        # Spec 016: channels that push messages (re-engagement goes out through them).
        self._deliveries: dict[str, Delivery] = {}

    def register_delivery(self, channel: Channel, delivery: Delivery) -> None:
        self._deliveries[channel] = delivery

    def now(self) -> datetime:
        return self._clock()

    def with_agent(self, agent: ScreeningAgent) -> "ScreeningService":
        """The same database, slots and clock behind another agent (the offline demo seed)."""
        service = ScreeningService(
            agent,
            self._sessions,
            self._slots,
            self._clock,
            self._staffing_seed,
            self._reengagement,
            self._public_base_url,
        )
        service._deliveries = self._deliveries
        return service

    async def init_zone_staffing(self) -> bool:
        """Seed `zone_staffing` from config if the table is empty (spec 015 FR-1).

        Idempotent: after the first start the database is the source of truth, so edits
        made in the dashboard are never overwritten by the YAML. True if it inserted.
        """
        if self._staffing_seed is None:
            return False
        async with self._sessions.begin() as session:
            return await insert_seed(session, self._staffing_seed, self._clock())

    async def init_interview_availability(self) -> list[str]:
        """Spec 010 FR-1: seed availability for configured cities without a row yet."""
        async with self._sessions.begin() as session:
            return await self._slots.init_availability(session, self._clock())

    @property
    def slots(self) -> SlotProvider:
        return self._slots

    def timezone_name(self, city: str) -> str:
        """The city's IANA timezone (service_areas.yaml); UTC for an unknown city."""
        tz = self._slots.timezone(city)
        return tz.key if tz else "UTC"

    async def interview_ics(self, conversation_id: str) -> str | None:
        """FR-5: the candidate's live booking as an .ics invite, in their language and
        register; None when they have no booked interview."""
        async with self._sessions() as session:
            row = await self._get(session, conversation_id)
            booking = await repo.active_booking(session, conversation_id)
        if booking is None:
            return None
        config = self._agent.engine_config
        register = register_for(
            Language(row.language),
            Country(row.country) if row.country else None,
            None,
            default_country=config.screening.default_country,
        )
        texts = self._agent.catalog.for_register(register).templates.interview
        return build_ics(
            CalendarEvent(
                uid=f"interview-{booking.id}@gruposazon.example",
                starts_at=booking.starts_at,
                ends_at=booking.starts_at + timedelta(minutes=booking.duration_min),
                stamp=booking.created_at,
                summary=texts.calendar_summary,
                location=booking.place,
                description=texts.calendar_description,
            )
        )

    # --- candidate side ------------------------------------------------------------------

    async def start_conversation(
        self,
        language: Language = Language.es,
        country_hint: Country | None = None,
        *,
        conversation_id: str | None = None,
        at: datetime | None = None,
        channel: Channel = "web",
    ) -> str:
        """FR-1: store a new conversation with Sofi's greeting; returns its id.
        `channel` is only for demo data (spec 016): real WhatsApp ones use `start_whatsapp`."""
        conversation_id, _ = await self._open(
            language,
            country_hint,
            conversation_id or str(uuid4()),
            at or self._clock(),
            channel=channel,
        )
        return conversation_id

    async def start_whatsapp(
        self,
        phone: str,
        first_message: str,
        *,
        language: Language = Language.es,
        country_hint: Country | None = None,
        at: datetime | None = None,
    ) -> tuple[str, OutboundMessage | None]:
        """Spec 016 FR-3: a new number wrote. The candidate writes first, so their message
        (e.g. "Hola") is stored before the greeting and opens the 24 h window. Returns
        the conversation id and the greeting to send."""
        conversation_id, result = await self._open(
            language,
            country_hint,
            str(uuid4()),
            at or self._clock(),
            channel="whatsapp",
            phone=phone,
            first_message=first_message,
        )
        return conversation_id, result.reply

    async def _open(
        self,
        language: Language,
        country_hint: Country | None,
        conversation_id: str,
        now: datetime,
        *,
        channel: Channel = "web",
        phone: str | None = None,
        first_message: str | None = None,
    ) -> tuple[str, TurnResult]:
        context = self._context(country_hint, now)
        result = await self._agent.start_conversation(
            language=language, context=context, conversation_id=conversation_id
        )
        async with self._sessions.begin() as session:
            conversation = Conversation(
                id=conversation_id,
                created_at=now,
                recruiter_status="new",
                channel=channel,
                phone=phone,
            )
            if first_message is not None:
                self._candidate_wrote(conversation, now)
            self._copy_state(conversation, result.state, now)
            repo.add(session, conversation)
            self._add_messages(session, conversation_id, first_message, result, now)
        return conversation_id, result

    async def send_message(
        self,
        conversation_id: str,
        text: str,
        *,
        at: datetime | None = None,
        kind: Literal["text", "media"] = "text",
    ) -> TurnOutcome:
        """FR-2: one candidate turn. A closed conversation still answers (the engine acks).

        `kind="media"`: the channel says it was a voice note or a photo (spec 016 FR-4);
        `text` is then only the placeholder stored in the transcript.
        """
        async with self._locks[conversation_id]:
            now = at or self._clock()
            state, history = await self._load(conversation_id)
            context = await self._turn_context(state, conversation_id, now)
            result = await self._agent.handle_message(
                state,
                InboundMessage(text=text, kind=kind),
                history,
                today=now.date(),
                context=context,
                conversation_id=conversation_id,
            )
            return await self._save_turn(conversation_id, text, result, now, before=state)

    async def send_event(
        self, conversation_id: str, event: Event, *, at: datetime | None = None
    ) -> TurnOutcome:
        """FR-13: timer and calendar events (008's scheduler sends silence_expired itself)."""
        async with self._locks[conversation_id]:
            return await self._event(conversation_id, event, at or self._clock())

    async def _event(self, conversation_id: str, event: Event, now: datetime) -> TurnOutcome:
        """`send_event` without the lock: the caller holds it."""
        state, _ = await self._load(conversation_id)
        result = await self._agent.handle_event(
            state,
            event,
            today=now.date(),
            context=await self._turn_context(state, conversation_id, now),
            conversation_id=conversation_id,
        )
        return await self._save_turn(conversation_id, None, result, now, before=state)

    # --- WhatsApp (spec 016) -------------------------------------------------------------

    async def conversation_for_phone(self, phone: str) -> str | None:
        async with self._sessions() as session:
            row = await repo.latest_conversation_for_phone(session, phone)
        return row.id if row else None

    async def quick_reply_label(self, conversation_id: str, reply_id: str) -> str | None:
        """The label of a quick reply Sofi offered (FR-4): a tapped WhatsApp button returns
        its id and a title that may have been shortened; the pipeline gets the full label,
        exactly as if the candidate had typed it. The latest offer of that id wins."""
        async with self._sessions() as session:
            messages = await repo.list_messages(session, conversation_id)
        for message in reversed(messages):
            if message.role != "agent":
                continue
            for option in message.quick_replies_json or []:
                if option.get("id") == reply_id:
                    return option.get("label")
        return None

    async def is_do_not_contact(self, phone: str) -> bool:
        async with self._sessions() as session:
            return await repo.is_do_not_contact(session, phone_hash(phone))

    async def claim_inbound(self, message_id: str, *, at: datetime | None = None) -> bool:
        """FR-2: True the first time a WhatsApp message id is seen, False on a redelivery.
        The primary key makes it atomic, even across processes sharing the database."""
        try:
            async with self._sessions.begin() as session:
                repo.add(session, InboundSeen(message_id=message_id, received_at=at or self.now()))
        except IntegrityError:
            return False
        return True

    # --- re-engagement (spec 008) --------------------------------------------------------

    @property
    def reengagement(self) -> ReengagementConfig | None:
        """The schedule in force (time-scaled), or None when reminders are off."""
        cfg = self._reengagement
        return cfg if cfg is not None and cfg.enabled else None

    async def due_for_reengagement(self, now: datetime) -> list[str]:
        """Conversations whose next step is due. A cheap pre-check without the lock: each
        one is checked again under its lock by `reengage`."""
        cfg = self.reengagement
        if cfg is None:
            return []
        async with self._sessions() as session:
            rows = await repo.waiting_conversations(session, Status.in_progress.value)
        return [row.id for row in rows if self._plan(row, cfg).at <= now]

    async def next_reengagement(self, conversation_id: str) -> Planned | None:
        """The next step for a conversation waiting for the candidate, due or not."""
        cfg = self.reengagement
        async with self._sessions() as session:
            row = await self._get(session, conversation_id)
        if cfg is None or row.status != Status.in_progress:
            return None
        return self._plan(row, cfg)

    async def reengage(
        self, conversation_id: str, *, force: bool = False, at: datetime | None = None
    ) -> Reengaged:
        """Run the next step if it is due (`force`: now, whatever the schedule says).

        Under the conversation's lock, so a candidate's message and a reminder never
        race, and with a compare-and-set on the step, so it is sent at most once.
        """
        now = at or self._clock()
        async with self._locks[conversation_id]:
            outcome = await self._reengage(conversation_id, force=force, now=now)
        await self._deliver_reengagement(conversation_id, outcome, now)
        return outcome

    async def _deliver_reengagement(
        self, conversation_id: str, outcome: Reengaged, now: datetime
    ) -> None:
        """Spec 016 FR-6: a reminder (or the abandon's close) for a WhatsApp conversation
        goes out through WhatsApp. Outside the lock: a slow Graph API never blocks the
        candidate's next message. Never raises: the step is already stored."""
        if outcome.reply is None or outcome.action == "none" or not self._deliveries:
            return
        try:
            async with self._sessions() as session:
                row = await self._get(session, conversation_id)
            delivery = self._deliveries.get(row.channel)
            if delivery is None:
                return
            cfg = self.reengagement
            opened = row.last_candidate_at
            outside = (
                outcome.requires_template
                if outcome.action == "follow_up"
                else opened is None or (cfg is not None and now > opened + cfg.window)
            )
            await delivery.deliver(
                Outbound(
                    conversation_id=conversation_id,
                    phone=row.phone,
                    reply=outcome.reply,
                    kind="follow_up" if outcome.action == "follow_up" else "close",
                    outside_window=outside,
                )
            )
        except Exception:
            logger.exception("re-engagement delivery failed (conversation %s)", conversation_id)

    async def _reengage(self, conversation_id: str, *, force: bool, now: datetime) -> Reengaged:
        async with self._sessions() as session:
            row = await self._get(session, conversation_id)
            messages = await repo.list_messages(session, conversation_id)
        status = Status(row.status)
        cfg = self.reengagement
        if cfg is None:
            return Reengaged(action="none", status=status, reason="disabled")
        if status is not Status.in_progress:  # closed, abandoned or opted out (FR-2)
            return Reengaged(action="none", status=status, reason="closed")
        if not messages or messages[-1].role != "agent":  # their turn is being answered
            return Reengaged(action="none", status=status, reason="candidate_last")
        planned = self._plan(row, cfg)
        if not force and planned.at > now:
            return Reengaged(action="none", status=status, reason="not_due", planned=planned)
        if isinstance(planned, Abandon):  # FR-5: the engine closes it, records the stage
            outcome = await self._event(conversation_id, SilenceExpired(), now)
            return Reengaged(
                action="abandon",
                status=outcome.status,
                reply=outcome.result.reply,
                summary_due=outcome.result.summary_due,
            )
        state = ConversationState.model_validate(row.state_json)
        result = await self._agent.follow_up(
            state,
            step=planned.step,
            kind=planned.kind,
            requires_template=planned.requires_template,
            recent_agent=tuple(m.text for m in messages if m.role == "agent"),
            conversation_id=conversation_id,
        )
        trace = result.trace
        async with self._sessions.begin() as session:
            claimed = await repo.claim_follow_up(
                session,
                conversation_id,
                expected_sent=row.follow_ups_sent,
                expected_last_candidate_at=row.last_candidate_at,
                at=now,
            )
            if claimed:
                message = Message(
                    conversation_id=conversation_id,
                    role="agent",
                    kind="follow_up",
                    follow_up_step=planned.step,
                    text=result.reply.text,
                    quick_replies_json=[],
                    created_at=now,
                    trace_json=trace.model_dump(mode="json"),
                    cost_usd=trace.cost_usd,
                    latency_ms=trace.latency_ms,
                    fallback=trace.phrasing.outcome == "fallback",
                )
                repo.add(session, message)
        if not claimed:
            logger.warning("follow-up %s already sent (conversation %s)", planned.step, row.id)
            return Reengaged(action="none", status=status, reason="already_sent")
        return Reengaged(
            action="follow_up",
            status=status,
            step=planned.step,
            reply=result.reply,
            requires_template=planned.requires_template,
        )

    def _plan(self, row: Conversation, cfg: ReengagementConfig) -> Planned:
        silence = Silence(
            started_at=row.created_at,
            last_candidate_at=row.last_candidate_at,
            steps_sent=row.follow_ups_sent or 0,
            last_follow_up_at=row.last_follow_up_at,
        )
        return next_step(cfg, silence, self._timezone(row, cfg))

    def _timezone(self, row: Conversation, cfg: ReengagementConfig) -> ZoneInfo:
        config = self._agent.engine_config
        return timezone_for(
            cfg,
            config.service_areas,
            city_id=row.city,
            country=Country(row.country) if row.country else None,
            default_country=config.screening.default_country,
        )

    # --- interview reminders (spec 010 FR-6) ---------------------------------------------

    async def due_interview_reminders(self, now: datetime) -> list[int]:
        """Bookings whose day-before reminder is due. A cheap pre-check; each one is checked
        again, and claimed, by `send_interview_reminder`."""
        if not self._slots.config.reminder.enabled:
            return []
        async with self._sessions() as session:
            rows = await repo.reminder_candidates(
                session, after=now, before=now + timedelta(days=2)
            )
        return [row.id for row in rows if self._reminder_due(row, now)]

    async def send_interview_reminder(
        self, booking_id: int, *, at: datetime | None = None
    ) -> OutboundMessage | None:
        """Send one booking's reminder if it is due: stored in the transcript and pushed
        through the conversation's channel (WhatsApp: the approved template outside the
        24 h window). At most once per booking (compare-and-set), under the conversation's
        lock so it never races a candidate's message. None: not due or already sent."""
        now = at or self._clock()
        async with self._sessions() as session:
            booking = await repo.get_booking(session, booking_id)
        if booking is None:
            return None
        conversation_id = booking.conversation_id
        async with self._locks[conversation_id], self._sessions.begin() as session:
            booking = await repo.get_booking(session, booking_id)
            if booking is None or not self._reminder_due(booking, now):
                return None
            if not await repo.claim_reminder(session, booking_id, now):
                logger.info("interview reminder already sent (conversation %s)", conversation_id)
                return None
            row = await self._get(session, conversation_id)
            state = ConversationState.model_validate(row.state_json)
            tz = self._slots.timezone(booking.city)
            local = booking.starts_at.astimezone(tz) if tz else booking.starts_at
            reply = self._agent.interview_reminder(
                state, time=local.strftime("%H:%M"), place=booking.place
            )
            repo.add(
                session,
                Message(
                    conversation_id=conversation_id,
                    role="agent",
                    kind="reminder",
                    text=reply.text,
                    quick_replies_json=[],
                    created_at=now,
                ),
            )
            channel, phone, opened = row.channel, row.phone, row.last_candidate_at
        logger.info("interview reminder sent (conversation %s)", conversation_id)
        await self._deliver(
            conversation_id, channel, phone, reply, kind="reminder", opened=opened, now=now
        )
        return reply

    async def mark_attendance(
        self, booking_id: int, status: AttendanceStatus, *, at: datetime | None = None
    ) -> InterviewBooking:
        """FR-7: a recruiter marks a past interview attended / no-show; `booked` undoes it.
        NotAllowed for a cancelled or moved booking, or one that has not started yet."""
        now = at or self._clock()
        async with self._sessions.begin() as session:
            booking = await repo.get_booking(session, booking_id)
            if booking is None:
                raise BookingNotFound(booking_id)
            if booking.status not in SEAT_HOLDING:
                raise NotAllowed(f"the booking was {booking.status}")
            if status != "booked" and booking.starts_at > now:
                raise NotAllowed("the interview has not happened yet")
            booking.status = status
            booking.updated_at = now
        return booking

    async def past_bookings(self, now: datetime) -> list[int]:
        """Live bookings whose interview has started (to mark them; the demo seed)."""
        async with self._sessions() as session:
            return [b.id for b in await repo.started_bookings(session, before=now)]

    def _reminder_due(self, booking: InterviewBooking, now: datetime) -> bool:
        tz = self._slots.timezone(booking.city)
        if booking.status != "booked" or booking.reminder_sent_at is not None or tz is None:
            return False
        cfg = self._reengagement
        return reminder_due(
            starts_at=booking.starts_at,
            booked_at=booking.created_at,
            now=now,
            tz=tz,
            config=self._slots.config.reminder,
            quiet_hours=cfg.quiet_hours if cfg is not None else None,
        )

    async def _deliver(
        self,
        conversation_id: str,
        channel: str,
        phone: str | None,
        reply: OutboundMessage,
        *,
        kind: DeliveryKind,
        opened: datetime | None,
        now: datetime,
    ) -> None:
        """Push a message through the conversation's channel (the web chat pulls instead).
        Never raises: the message is already stored."""
        delivery = self._deliveries.get(channel)
        if delivery is None:
            return
        window = self._reengagement.window if self._reengagement else timedelta(hours=24)
        try:
            await delivery.deliver(
                Outbound(
                    conversation_id=conversation_id,
                    phone=phone,
                    reply=reply,
                    kind=kind,
                    outside_window=opened is None or now > opened + window,
                )
            )
        except Exception:
            logger.exception("%s delivery failed (conversation %s)", kind, conversation_id)

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

    def _context(self, country_hint: Country | None, now: datetime) -> TurnContextIn:
        """A new conversation: nothing known yet (no city, so no slots)."""
        return TurnContextIn(country_hint=country_hint)

    async def _turn_context(
        self, state: ConversationState, conversation_id: str, now: datetime
    ) -> TurnContextIn:
        """What the caller knows this turn: staffing (015) and interview slots (010).

        Slots come from the candidate's city agenda, full ones left out (FR-2). A failed
        read must not break the turn: no slots are offered, so a candidate confirming the
        recap is `qualified_unscheduled` and a recruiter books them.
        """
        zone_full = await self._zone_full(state, conversation_id)
        location = state.profile.location.value
        city = location.city if location else None
        slots: list[SlotDisplay] = []
        known: list[SlotDisplay] = []
        channel: str | None = None
        try:
            async with self._sessions() as session:
                if city is not None:
                    slots = await self._slots.offer(session, city, now)
                earlier = [*state.offered_slot_ids, *filter(None, [state.selected_slot_id])]
                known = await self._slots.describe(session, earlier)
                row = await repo.get_conversation(session, conversation_id)
                channel = row.channel if row else None
        except Exception:
            logger.exception("interview slots lookup failed (conversation %s)", conversation_id)
        return TurnContextIn(
            country_hint=state.country_hint,
            slots=slots,
            known_slots=known,
            zone_full=zone_full,
            calendar_url=self._calendar_url(conversation_id, channel),
        )

    def _calendar_url(self, conversation_id: str, channel: str | None) -> str | None:
        """FR-5: WhatsApp confirmations link the .ics when the API is publicly reachable;
        the web chat shows its own button from the conversation's booking."""
        if self._public_base_url is None or channel != "whatsapp":
            return None
        return f"{self._public_base_url}{ics_path(conversation_id)}"

    async def _load(self, conversation_id: str) -> tuple[ConversationState, list[TranscriptEntry]]:
        async with self._sessions() as session:
            conversation = await self._get(session, conversation_id)
            messages = await repo.list_messages(session, conversation_id)
        state = ConversationState.model_validate(conversation.state_json)
        return state, [_entry(m) for m in messages]

    async def _save_turn(
        self,
        conversation_id: str,
        text: str | None,
        result: TurnResult,
        now: datetime,
        *,
        before: ConversationState | None = None,
    ) -> TurnOutcome:
        """Store the turn. If it books a slot that filled up meanwhile (FR-3, AC-2), the
        engine is told (`slot_taken`, with the slots still open) and that turn is stored
        instead: the candidate hears "that slot was just taken" and gets fresh slots."""
        try:
            return await self._commit_turn(conversation_id, text, result, now, before)
        except SlotUnavailable as taken:
            assert before is not None  # only a turn that changes the booking can raise it
            logger.info("slot %s taken meanwhile (conversation %s)", taken.slot_id, conversation_id)
            context = await self._turn_context(before, conversation_id, now)
            open_ids = [slot.id for slot in context.slots or []]
            retry = await self._agent.handle_event(
                before,
                SlotTaken(slot_id=taken.slot_id, slot_ids=open_ids),
                today=now.date(),
                context=context,
                conversation_id=conversation_id,
            )
            return await self._commit_turn(conversation_id, text, retry, now, before)

    async def _commit_turn(
        self,
        conversation_id: str,
        text: str | None,
        result: TurnResult,
        now: datetime,
        before: ConversationState | None,
    ) -> TurnOutcome:
        """One transaction: messages, state and booking. A lost race for a seat (unique
        index; SQLite may report it as a busy snapshot) is retried with a fresh count."""
        books = before is not None and before.selected_slot_id != result.state.selected_slot_id
        attempt = 1
        while True:
            try:
                return await self._write_turn(conversation_id, text, result, now, before)
            except (IntegrityError, OperationalError) as error:
                if not books:
                    raise
                if attempt == BOOKING_ATTEMPTS:
                    raise SlotUnavailable(result.state.selected_slot_id or "") from error
                logger.info(
                    "booking race, retrying %d/%d (conversation %s): %s",
                    attempt,
                    BOOKING_ATTEMPTS,
                    conversation_id,
                    type(error).__name__,
                )
                await asyncio.sleep(BOOKING_BACKOFF_S * attempt)
                attempt += 1

    async def _write_turn(
        self,
        conversation_id: str,
        text: str | None,
        result: TurnResult,
        now: datetime,
        before: ConversationState | None,
    ) -> TurnOutcome:
        async with self._sessions.begin() as session:
            conversation = await self._get(session, conversation_id)
            previous = conversation.status
            if before is not None:
                await sync_booking(
                    session,
                    self._slots,
                    conversation_id,
                    before=before.selected_slot_id,
                    after=result.state.selected_slot_id,
                    now=now,
                )
            self._add_messages(session, conversation_id, text, result, now)
            if text is not None:
                self._candidate_wrote(conversation, now)
            staffing = await load_staffing(session)
            self._copy_state(conversation, result.state, now, staffing)
            if conversation.status != previous:
                await repo.delete_summaries(session, conversation_id)  # they describe the past
            if result.state.status is Status.opted_out:
                await repo.redact_messages(session, conversation_id)  # 002 FR-11
                await self._do_not_contact(session, conversation, now)
        if result.state.last_error:
            logger.error(
                "engine error %s (conversation %s)", result.state.last_error, conversation_id
            )
        return TurnOutcome(result=result, status=result.state.status)

    async def _do_not_contact(
        self, session: AsyncSession, conversation: Conversation, now: datetime
    ) -> None:
        """Spec 016 FR-3: an opted-out number is never messaged again. Only its hash is
        kept; the number itself is erased with the rest of the PII (002 FR-11)."""
        if conversation.phone is None:
            return
        await repo.add_do_not_contact(session, phone_hash(conversation.phone), now)
        logger.info(
            "do-not-contact %s (conversation %s)", phone_ref(conversation.phone), conversation.id
        )
        conversation.phone = None

    @staticmethod
    def _candidate_wrote(conversation: Conversation, now: datetime) -> None:
        """Spec 008 FR-2, FR-6: any message resets the silence; note the reminder (if
        any) the candidate came back after."""
        if conversation.follow_ups_sent:
            conversation.reactivated_after_step = conversation.follow_ups_sent
        conversation.follow_ups_sent = 0
        conversation.last_follow_up_at = None
        conversation.last_candidate_at = now

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


def ics_path(conversation_id: str) -> str:
    """FR-5: where a candidate's calendar invite is served (relative to the API root)."""
    return f"/api/interviews/{conversation_id}.ics"


def _entry(message: Message) -> TranscriptEntry:
    return TranscriptEntry(
        role="candidate" if message.role == "candidate" else "agent", text=message.text
    )


def summary_of(row: SummaryRow) -> Summary:
    return Summary.model_validate(row.json)
