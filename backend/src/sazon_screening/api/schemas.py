"""Request and response models: the HTTP contract the frontend (005, 006) is built on."""

from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from sazon_screening.api.models import (
    Conversation,
    InterviewBooking,
    Message,
    RecruiterAction,
    SummaryRow,
)
from sazon_screening.api.service import ActionName, Channel, Reengaged, TurnOutcome
from sazon_screening.api.staffing import Staffing, area_of_row, live_score
from sazon_screening.config import EngineConfig
from sazon_screening.engine import CandidateRecord, ScoreResult
from sazon_screening.llm.summary.facts import SummaryFact
from sazon_screening.llm.summary.summarizer import NarrativeOutput
from sazon_screening.reengagement import Planned, SendFollowUp
from sazon_screening.scheduling import parse_slot_id
from sazon_screening.vocab import (
    Availability,
    Bucket,
    Country,
    DisqualificationReason,
    Flag,
    Language,
    ScheduleSlot,
    Status,
    VehicleType,
)

RecruiterStatus = Literal["new", "shortlisted", "rejected", "hired"]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- candidate chat (FR-1..3) ----------------------------------------------------------


class CreateConversationIn(_In):
    language: Language = Language.es
    country_hint: Country | None = None  # e.g. from the phone prefix


class SendMessageIn(_In):
    text: Text  # a quick-reply tap is sent as its label


class QuickReplyOut(BaseModel):
    id: str
    label: str


MessageKind = Literal["reply", "follow_up"]


class MessageOut(BaseModel):
    id: int
    role: Literal["candidate", "agent"]
    text: str
    quick_replies: list[QuickReplyOut]
    created_at: datetime
    # Spec 008: "follow_up" is a reminder Sofi sent after a silence (agent messages only).
    kind: MessageKind = "reply"
    follow_up_step: int | None = None  # 1-based within that silence; None for replies
    requires_template: bool = False  # past WhatsApp's 24 h window: an approved template

    @classmethod
    def of(cls, row: Message) -> Self:
        follow_up = (row.trace_json or {}).get("follow_up") or {}
        return cls(
            id=row.id,
            role="candidate" if row.role == "candidate" else "agent",
            text=row.text,
            quick_replies=[QuickReplyOut(**q) for q in row.quick_replies_json],
            created_at=row.created_at,
            kind="follow_up" if row.kind == "follow_up" else "reply",
            follow_up_step=row.follow_up_step,
            requires_template=bool(follow_up.get("requires_template", False)),
        )


BookingStatus = Literal["booked", "attended", "no_show", "cancelled", "rescheduled"]


class BookingOut(BaseModel):
    """One interview booking (spec 010). Times are UTC; `local_start` is the wall clock in
    the city (`timezone`), which is what candidates and recruiters read."""

    id: int
    slot_id: str  # "madrid:2026-10-20T10:00"
    city: str
    local_start: str  # "2026-10-20T10:00"
    timezone: str  # IANA, e.g. "Europe/Madrid"
    starts_at: datetime
    ends_at: datetime
    duration_min: int
    place: str
    status: BookingStatus
    ics_url: str  # relative to the API root, e.g. "/api/interviews/<conversation id>.ics"
    reminder_sent_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, row: InterviewBooking, timezone: str) -> Self:
        slot = parse_slot_id(row.slot_id)
        local = f"{slot.day.isoformat()}T{slot.time}" if slot else row.slot_id
        return cls.model_validate(
            {
                "id": row.id,
                "slot_id": row.slot_id,
                "city": row.city,
                "local_start": local,
                "timezone": timezone,
                "starts_at": row.starts_at,
                "ends_at": row.starts_at + timedelta(minutes=row.duration_min),
                "duration_min": row.duration_min,
                "place": row.place,
                "status": row.status,
                "ics_url": f"/api/interviews/{row.conversation_id}.ics",
                "reminder_sent_at": row.reminder_sent_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )


class ConversationOut(BaseModel):
    id: str
    status: Status
    language: Language
    messages: list[MessageOut]
    # Spec 010: the live interview booking, if any (the chat's "Añadir al calendario").
    booking: BookingOut | None = None


class ReplyOut(BaseModel):
    text: str
    quick_replies: list[QuickReplyOut]


class TurnOut(BaseModel):
    reply: ReplyOut | None  # None: the agent sends nothing this turn
    status: Status

    @classmethod
    def of(cls, outcome: TurnOutcome) -> Self:
        reply = outcome.result.reply
        return cls(
            reply=ReplyOut(
                text=reply.text,
                quick_replies=[QuickReplyOut(**q.model_dump()) for q in reply.quick_replies],
            )
            if reply
            else None,
            status=outcome.status,
        )


# --- recruiter dashboard (FR-6..10) ----------------------------------------------------


class CandidateRow(BaseModel):
    id: str
    full_name: str | None
    country: Country | None
    city: str | None  # config ids (service_areas.yaml)
    zone: str | None
    status: Status
    disqualification_reason: DisqualificationReason | None
    bucket: Bucket | None  # live: zone demand at today's occupancy (spec 015 FR-6)
    score: int | None  # live
    score_at_close: int | None  # as stored when the conversation last changed (audit)
    bucket_at_close: Bucket | None
    vehicle_type: VehicleType | None
    availability: list[Availability] | None
    schedule: list[ScheduleSlot] | None
    experience_years: int | None
    platforms: list[str] | None
    start_date: date | None
    start_date_approximate: bool  # month-level ("el mes que viene"): show the month only
    language: Language
    channel: Channel  # spec 016: where the candidate talks to Sofi (never their number)
    interview_slot: str | None  # ISO local date-time in the city, e.g. "2026-10-13T10:00"
    interview_slot_id: str | None  # spec 010: the slot id, e.g. "madrid:2026-10-13T10:00"
    recruiter_status: RecruiterStatus
    recruiter_override: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, row: Conversation, *, staffing: Staffing, config: EngineConfig) -> Self:
        return cls.from_record(
            row, CandidateRecord.model_validate(row.record_json), staffing=staffing, config=config
        )[0]

    @classmethod
    def from_record(
        cls,
        row: Conversation,
        record: CandidateRecord,
        *,
        staffing: Staffing,
        config: EngineConfig,
    ) -> tuple[Self, ScoreResult | None]:
        """The row, plus the live score it shows (the detail view lists its factors)."""
        live = live_score(record, area_of_row(row), staffing, config)
        fields = record.fields
        experience = fields.experience.value
        candidate = cls.model_validate(
            {
                "id": row.id,
                "full_name": row.full_name,
                "country": row.country,
                "city": row.city,
                "zone": row.zone,
                "status": row.status,
                "disqualification_reason": row.disqualification_reason,
                "bucket": live.bucket if live else None,
                "score": live.score if live else None,
                "score_at_close": row.score,
                "bucket_at_close": row.bucket,
                "vehicle_type": fields.vehicle_type.value,
                "availability": fields.availability.value,
                "schedule": fields.schedule.value,
                "experience_years": experience.years if experience else None,
                "platforms": experience.platforms if experience else None,
                "start_date": fields.start_date.value,
                "start_date_approximate": Flag.start_date_approximate in record.flags,
                "language": row.language,
                "channel": row.channel,
                "interview_slot": _local_part(row.interview_slot),
                "interview_slot_id": row.interview_slot,
                "recruiter_status": row.recruiter_status,
                "recruiter_override": row.recruiter_override,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )
        return candidate, live


def _local_part(slot_id: str | None) -> str | None:
    """'madrid:2026-10-13T10:00' -> '2026-10-13T10:00' (the city's wall clock)."""
    slot = parse_slot_id(slot_id) if slot_id else None
    return f"{slot.day.isoformat()}T{slot.time}" if slot else slot_id


class SummaryOut(BaseModel):
    language: Language
    status: Status  # the status it describes
    generated_by: Literal["llm", "template"]
    text: str  # markdown: facts, then the narrative
    facts: list[SummaryFact]
    narrative: NarrativeOutput | None
    created_at: datetime

    @classmethod
    def of(cls, row: SummaryRow) -> Self:
        return cls.model_validate(row.json | {"created_at": row.created_at})


class TraceOut(BaseModel):
    """One agent turn, for the dashboard's "how did the agent get here" view."""

    message_id: int
    created_at: datetime
    kind: MessageKind = "reply"  # spec 008: a reminder has a trace too (no engine action)
    action: str | None  # the engine's primary action, e.g. "ask_field"; "follow_up" (008)
    client: str  # "anthropic" | "fake-rules" | ...
    models: dict[str, str]
    latency_ms: int
    cost_usd: float
    fallback: bool  # the reply is the template, not the model's text
    extraction: str  # "ok" | "failed" | "skipped"
    # Spec 009: the candidate asked something; "unanswered" is flagged for the recruiter.
    # The question, retrieved ids and scores are in `trace["faq"]`.
    faq: Literal["answered", "unanswered"] | None = None
    trace: dict[str, Any]  # the full turn trace (spec 003)

    @classmethod
    def of(cls, row: Message) -> Self | None:
        trace = row.trace_json
        if trace is None:
            return None
        action = trace.get("action")
        follow_up = "follow_up" in trace
        return cls(
            message_id=row.id,
            created_at=row.created_at,
            kind="follow_up" if follow_up else "reply",
            action="follow_up" if follow_up else action["primary"]["type"] if action else None,
            client=trace["client"],
            models=trace["models"],
            latency_ms=row.latency_ms or 0,
            cost_usd=row.cost_usd,
            fallback=row.fallback,
            extraction=(trace.get("extraction") or {}).get("outcome", "skipped"),
            faq=(trace.get("faq") or {}).get("outcome"),
            trace=trace,
        )


class ActionIn(_In):
    action: ActionName
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None

    @model_validator(mode="after")
    def _note_has_text(self) -> Self:
        if self.action == "note" and not self.note:
            raise ValueError("a note needs text")
        return self


class ActionOut(BaseModel):
    id: int
    action: ActionName
    note: str | None
    created_at: datetime

    @classmethod
    def of(cls, row: RecruiterAction) -> Self:
        return cls.model_validate(
            {"id": row.id, "action": row.action, "note": row.note, "created_at": row.created_at}
        )


class NextStepOut(BaseModel):
    """Spec 008: what re-engagement does next if the candidate stays quiet."""

    action: Literal["follow_up", "abandon"]
    step: int | None  # the reminder number; None for the abandon
    at: datetime  # when (time-scaled in a demo); may be in the past until the next tick
    requires_template: bool

    @classmethod
    def of(cls, planned: Planned) -> Self:
        if isinstance(planned, SendFollowUp):
            return cls(
                action="follow_up",
                step=planned.step,
                at=planned.at,
                requires_template=planned.requires_template,
            )
        return cls(action="abandon", step=None, at=planned.at, requires_template=False)


class ReengagementOut(BaseModel):
    """Spec 008 FR-9: the reminders a candidate got and whether they came back."""

    follow_ups_sent: int  # reminders in this conversation, over every silence
    waiting_steps: int  # reminders since the candidate last wrote
    last_follow_up_at: datetime | None
    reactivated_after_step: int | None  # the candidate came back after this reminder
    next: NextStepOut | None  # only while in progress and waiting for the candidate
    total_steps: int  # reminders in the configured schedule (0: re-engagement disabled)


class CandidateDetail(BaseModel):
    candidate: CandidateRow
    record: CandidateRecord  # spec 002 schema; `record.score` is the score at close
    live_score: ScoreResult | None  # the same factors, zone demand at today's occupancy
    summary: SummaryOut | None  # default language; None while in progress or being written
    transcript: list[MessageOut]
    traces: list[TraceOut]
    actions: list[ActionOut]  # oldest first
    reengagement: ReengagementOut


# --- analytics (FR-11) -----------------------------------------------------------------


class FaqQuestionCount(BaseModel):
    entry_id: str | None  # None: no approved answer matched (flagged for a recruiter)
    question: str  # the entry's own question, or the candidate's words when unanswered
    count: int


class FaqAnalytics(BaseModel):
    """Spec 009: what candidates ask and how often Sofi had no approved answer."""

    asked: int  # agent turns that answered a candidate's question
    answered: int  # from the approved FAQ
    unanswered_rate: float  # (asked - answered) / asked: the gaps in the FAQ
    top_questions: list[FaqQuestionCount]  # most asked first


class ReengagementStepCount(BaseModel):
    step: int
    sent: int  # reminders with this number
    reactivated: int  # conversations whose candidate came back after this one


class ReengagementAnalytics(BaseModel):
    """Spec 008 FR-9. `sum(by_step.sent) == follow_ups_sent` and
    `sum(by_step.reactivated) == reactivated`."""

    follow_ups_sent: int
    conversations_nudged: int  # got at least one reminder
    reactivated: int  # came back after a reminder
    reactivation_rate: float  # reactivated / conversations_nudged
    by_step: list[ReengagementStepCount]


class Analytics(BaseModel):
    total: int
    by_status: dict[Status, int]
    finished: int  # reached an outcome: booked, qualified, waitlisted, disqualified, review
    completion_rate: float  # finished / total
    drop_off_by_stage: dict[str, int]  # abandoned conversations only
    median_duration_s: float | None  # finished conversations: first to last message
    disqualification_reasons: dict[DisqualificationReason, int]
    agent_turns: int
    fallback_rate: float  # agent replies that used the template instead of the model
    avg_cost_usd: float  # LLM cost per conversation, including summaries
    by_country: dict[str, dict[Status, int]]  # "unknown" when no country is known yet
    by_channel: dict[Channel, dict[Status, int]]  # spec 016: web chat vs WhatsApp
    faq: FaqAnalytics
    reengagement: ReengagementAnalytics


class AdvanceOut(BaseModel):
    """`POST /api/dev/conversations/{id}/advance`: the step that just ran (spec 008 FR-8)."""

    action: Literal["follow_up", "abandon"]
    status: Status
    step: int | None  # the reminder sent; None for the abandon
    reply: ReplyOut | None  # the reminder; on abandon, the engine's close message (if any)
    requires_template: bool
    next: NextStepOut | None  # what would come after, if the candidate stays quiet

    @classmethod
    def of(cls, outcome: Reengaged, planned: Planned | None) -> Self:
        assert outcome.action != "none"
        reply = outcome.reply
        return cls(
            action=outcome.action,
            status=outcome.status,
            step=outcome.step,
            reply=ReplyOut(
                text=reply.text,
                quick_replies=[QuickReplyOut(**q.model_dump()) for q in reply.quick_replies],
            )
            if reply
            else None,
            requires_template=outcome.requires_template,
            next=NextStepOut.of(planned) if planned else None,
        )


class SeedOut(BaseModel):
    created: int
    ids: list[str]


# --- zones (spec 015) --------------------------------------------------------------------


class ZonePipeline(BaseModel):
    """Qualified candidates in the area, by status."""

    qualified_unscheduled: int
    interview_scheduled: int
    waitlisted: int


class ZoneOut(BaseModel):
    """One served area: a zone, or a city served as a whole (then `id == city`)."""

    id: str
    name: str  # display name in the requested language, e.g. "Salamanca"
    city: str  # config city id
    city_name: str
    country: Country
    target_drivers: int | None  # None: no staffing data (no bonus, never waitlisted)
    current_drivers: int | None
    occupancy_pct: int | None  # current / target, rounded down; a target of 0 reads 100
    full: bool  # occupancy >= 100 %: new qualified candidates are waitlisted
    pipeline: ZonePipeline
    updated_at: datetime | None


class ZonePatchIn(_In):
    """Either or both. On an area without data, the missing number starts at 0."""

    target_drivers: int | None = Field(default=None, ge=0)
    current_drivers: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _something_to_change(self) -> Self:
        if self.target_drivers is None and self.current_drivers is None:
            raise ValueError("give target_drivers, current_drivers or both")
        return self


# --- labels for config ids ---------------------------------------------------------------


class AreaLabels(BaseModel):
    cities: dict[str, str]  # city id -> display name
    zones: dict[str, str]  # zone id -> display name
