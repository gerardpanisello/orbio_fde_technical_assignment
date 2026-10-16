"""Tables (spec 004 §3). Engine objects are stored as JSON; a few columns are copied out
of them (denormalised) only so the dashboard can filter and sort in SQL.

`state_json` is the source of truth to resume a conversation; `record_json` is the
002 candidate record. The denormalised columns are rewritten from them on every turn.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Dialect,
    ForeignKey,
    Index,
    String,
    Text,
    TypeDecorator,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class UTCDateTime(TypeDecorator[datetime]):
    """Stored as naive UTC (SQLite has no time zones), always read back as aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.astimezone(UTC).replace(tzinfo=None) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    # Copied from the state / record for filtering and sorting:
    status: Mapped[str] = mapped_column(String(32), index=True)
    stage: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(8))
    country: Mapped[str | None] = mapped_column(String(8), index=True)
    city: Mapped[str | None] = mapped_column(String(64), index=True)
    zone: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str | None] = mapped_column(String(200))
    score: Mapped[int | None]
    bucket: Mapped[str | None] = mapped_column(String(16), index=True)
    disqualification_reason: Mapped[str | None] = mapped_column(String(32))
    drop_off_stage: Mapped[str | None] = mapped_column(String(32))
    interview_slot: Mapped[str | None] = mapped_column(String(64))
    # Re-engagement (spec 008). Reset when the candidate writes; analytics count messages.
    last_candidate_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # None: never wrote
    follow_ups_sent: Mapped[int] = mapped_column(default=0)  # in the current silence
    last_follow_up_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reactivated_after_step: Mapped[int | None]  # the reminder the candidate came back after
    # Channel (spec 016 FR-6): "web" (the simulated chat) or "whatsapp".
    channel: Mapped[str] = mapped_column(String(16), default="web", index=True)
    # WhatsApp only: the candidate's wa_id (international number, digits), to reply and to
    # find the conversation again. Never copied into the state, record, transcript, summaries
    # or exports; cleared on opt-out (the do-not-contact set keeps only a hash).
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    # Recruiter side (FR-9):
    recruiter_status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    recruiter_override: Mapped[bool] = mapped_column(default=False)
    # Engine objects:
    state_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    record_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    flags_json: Mapped[list[str]] = mapped_column(JSON)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)  # transcript order
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # "candidate" | "agent"
    kind: Mapped[str] = mapped_column(String(16), default="reply")  # "reply" | "follow_up" (008)
    follow_up_step: Mapped[int | None]  # 1-based, follow-ups only
    text: Mapped[str] = mapped_column(Text)
    quick_replies_json: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # Agent turns only: the turn trace, plus the numbers analytics aggregates in SQL.
    trace_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    latency_ms: Mapped[int | None]
    fallback: Mapped[bool] = mapped_column(default=False)


class SummaryRow(Base):
    __tablename__ = "summaries"

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), primary_key=True)
    language: Mapped[str] = mapped_column(String(8), primary_key=True)
    json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    cost_usd: Mapped[float] = mapped_column(default=0.0)


class ZoneStaffing(Base):
    """Drivers per served area (spec 015). Seeded once from config/zone_staffing.yaml; then
    the source of truth, edited from the dashboard and by "hire" (+1)."""

    __tablename__ = "zone_staffing"

    area_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # zone or city id
    target_drivers: Mapped[int]
    current_drivers: Mapped[int]
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class RecruiterAction(Base):
    __tablename__ = "recruiter_actions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class InboundSeen(Base):
    """WhatsApp message ids already accepted (spec 016 FR-2): Meta may deliver one twice."""

    __tablename__ = "whatsapp_inbound_seen"

    message_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime)


class DoNotContact(Base):
    """Numbers that opted out (spec 001 FR-7/FR-11, 016 FR-3): never messaged again.

    Only the SHA-256 of the number is kept, so the set itself holds no phone numbers.
    """

    __tablename__ = "do_not_contact"

    phone_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class InterviewAvailability(Base):
    """When and where a city interviews (spec 010 FR-1). Seeded once per city from
    config/interview_slots.yaml; then the source of truth, edited from the dashboard."""

    __tablename__ = "interview_availability"

    city: Mapped[str] = mapped_column(String(64), primary_key=True)  # service_areas.yaml id
    weekdays_json: Mapped[list[str]] = mapped_column(JSON)  # ["mon", ...]
    times_json: Mapped[list[str]] = mapped_column(JSON)  # ["10:00", ...], local time
    capacity: Mapped[int]  # candidates per slot
    duration_min: Mapped[int]
    days_ahead: Mapped[int]
    place: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


# A booking holds a seat while it is booked or after it happened; a cancelled or moved one
# frees it. Both indexes below are partial on exactly these statuses.
SEAT_HOLDING = ("booked", "attended", "no_show")
_HOLDS_SEAT = text("status IN ('booked', 'attended', 'no_show')")
_BOOKED = text("status = 'booked'")


class InterviewBooking(Base):
    """One interview booking (spec 010 FR-3). Never deleted: a move or a cancel changes the
    status, so the history (reschedules, cancels, attendance) stays for the recruiter.

    No double booking (AC-2): a booking takes seat n (0 <= n < capacity) of its slot, and
    a UNIQUE index on (slot_id, seat) over seat-holding rows lets the database, not the
    application, refuse a second booking of the same seat. Two conversations racing for
    the last seat both try to insert it; one commit wins, the other gets an IntegrityError
    (Postgres; SQLite reports a busy snapshot or the same error) and retries: it re-counts
    the seats and finds the slot full. Partial unique indexes work on SQLite and Postgres.
    """

    __tablename__ = "interview_bookings"
    __table_args__ = (
        Index(
            "uq_interview_seat",
            "slot_id",
            "seat",
            unique=True,
            sqlite_where=_HOLDS_SEAT,
            postgresql_where=_HOLDS_SEAT,
        ),
        Index(  # one live booking per candidate
            "uq_interview_conversation",
            "conversation_id",
            unique=True,
            sqlite_where=_BOOKED,
            postgresql_where=_BOOKED,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    slot_id: Mapped[str] = mapped_column(String(96), index=True)  # "madrid:2026-10-20T10:00"
    city: Mapped[str] = mapped_column(String(64), index=True)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    duration_min: Mapped[int]
    place: Mapped[str] = mapped_column(String(200))  # as it was when booked
    seat: Mapped[int]
    # booked | attended | no_show | cancelled | rescheduled (moved to a newer booking)
    status: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # FR-6, once
