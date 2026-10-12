"""Request and response models: the HTTP contract the frontend (005, 006) is built on."""

from datetime import date, datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from sazon_screening.api.models import Conversation, Message, RecruiterAction, SummaryRow
from sazon_screening.api.service import ActionName, TurnOutcome
from sazon_screening.engine import CandidateRecord
from sazon_screening.llm.summary.facts import SummaryFact
from sazon_screening.llm.summary.summarizer import NarrativeOutput
from sazon_screening.vocab import (
    Availability,
    Bucket,
    Country,
    DisqualificationReason,
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


class MessageOut(BaseModel):
    id: int
    role: Literal["candidate", "agent"]
    text: str
    quick_replies: list[QuickReplyOut]
    created_at: datetime

    @classmethod
    def of(cls, row: Message) -> Self:
        return cls(
            id=row.id,
            role="candidate" if row.role == "candidate" else "agent",
            text=row.text,
            quick_replies=[QuickReplyOut(**q) for q in row.quick_replies_json],
            created_at=row.created_at,
        )


class ConversationOut(BaseModel):
    id: str
    status: Status
    language: Language
    messages: list[MessageOut]


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
    bucket: Bucket | None
    score: int | None
    vehicle_type: VehicleType | None
    availability: list[Availability] | None
    schedule: list[ScheduleSlot] | None
    experience_years: int | None
    platforms: list[str] | None
    start_date: date | None
    language: Language
    interview_slot: str | None  # ISO local date-time, e.g. "2026-10-13T10:00"
    recruiter_status: RecruiterStatus
    recruiter_override: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, row: Conversation) -> Self:
        fields = CandidateRecord.model_validate(row.record_json).fields
        experience = fields.experience.value
        return cls.model_validate(
            {
                "id": row.id,
                "full_name": row.full_name,
                "country": row.country,
                "city": row.city,
                "zone": row.zone,
                "status": row.status,
                "disqualification_reason": row.disqualification_reason,
                "bucket": row.bucket,
                "score": row.score,
                "vehicle_type": fields.vehicle_type.value,
                "availability": fields.availability.value,
                "schedule": fields.schedule.value,
                "experience_years": experience.years if experience else None,
                "platforms": experience.platforms if experience else None,
                "start_date": fields.start_date.value,
                "language": row.language,
                "interview_slot": row.interview_slot,
                "recruiter_status": row.recruiter_status,
                "recruiter_override": row.recruiter_override,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )


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
    action: str | None  # the engine's primary action, e.g. "ask_field"
    client: str  # "anthropic" | "fake-rules" | ...
    models: dict[str, str]
    latency_ms: int
    cost_usd: float
    fallback: bool  # the reply is the template, not the model's text
    extraction: str  # "ok" | "failed" | "skipped"
    trace: dict[str, Any]  # the full turn trace (spec 003)

    @classmethod
    def of(cls, row: Message) -> Self | None:
        trace = row.trace_json
        if trace is None:
            return None
        action = trace.get("action")
        return cls(
            message_id=row.id,
            created_at=row.created_at,
            action=action["primary"]["type"] if action else None,
            client=trace["client"],
            models=trace["models"],
            latency_ms=row.latency_ms or 0,
            cost_usd=row.cost_usd,
            fallback=row.fallback,
            extraction=trace["extraction"]["outcome"],
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


class CandidateDetail(BaseModel):
    candidate: CandidateRow
    record: CandidateRecord  # spec 002 schema
    summary: SummaryOut | None  # default language; None while in progress or being written
    transcript: list[MessageOut]
    traces: list[TraceOut]
    actions: list[ActionOut]  # oldest first


# --- analytics (FR-11) -----------------------------------------------------------------


class Analytics(BaseModel):
    total: int
    by_status: dict[Status, int]
    finished: int  # reached an outcome: booked, qualified, disqualified or needs_review
    completion_rate: float  # finished / total
    drop_off_by_stage: dict[str, int]  # abandoned conversations only
    median_duration_s: float | None  # finished conversations: first to last message
    disqualification_reasons: dict[DisqualificationReason, int]
    agent_turns: int
    fallback_rate: float  # agent replies that used the template instead of the model
    avg_cost_usd: float  # LLM cost per conversation, including summaries
    by_country: dict[str, dict[Status, int]]  # "unknown" when no country is known yet


class SeedOut(BaseModel):
    created: int
    ids: list[str]


# --- labels for config ids ---------------------------------------------------------------


class AreaLabels(BaseModel):
    cities: dict[str, str]  # city id -> display name
    zones: dict[str, str]  # zone id -> display name
