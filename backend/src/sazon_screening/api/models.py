"""Tables (spec 004 §3). Engine objects are stored as JSON; a few columns are copied out
of them (denormalised) only so the dashboard can filter and sort in SQL.

`state_json` is the source of truth to resume a conversation; `record_json` is the
002 candidate record. The denormalised columns are rewritten from them on every turn.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Dialect, ForeignKey, String, Text, TypeDecorator
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


class RecruiterAction(Base):
    __tablename__ = "recruiter_actions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
