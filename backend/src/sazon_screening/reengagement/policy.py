"""When the next follow-up (or the abandon) is due: pure time maths (spec 008 FR-2..FR-5).

No clock, no database: callers pass `now` and what they know about the silence, so every
rule is unit-tested with exact datetimes. All datetimes are timezone-aware; quiet hours
are evaluated in the candidate's local timezone, everything else is absolute time.

Schedule for step n (1-based) of the configured follow-ups:
- due at `last candidate message + after[n]` (each `after` counts from that message);
- never sooner than the previous follow-up + the configured gap between the two
  (a step postponed by quiet hours or by downtime does not drag the next one onto it);
- inside quiet hours -> postponed to their end, local time (FR-4);
- later than the WhatsApp window after the candidate's last message -> it must be an
  approved template (`requires_template`, FR-3). A candidate who never wrote never
  opened the window, so every follow-up to them is a template.
After the last step: abandon `abandon_after` after it was actually sent (FR-5).
"""

from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from sazon_screening.reengagement.config import QuietHours, ReengagementConfig


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Silence(_Frozen):
    """What we know about a conversation that is waiting for the candidate."""

    started_at: AwareDatetime  # the conversation (Sofi's greeting)
    last_candidate_at: AwareDatetime | None  # None: the candidate never wrote
    steps_sent: int = Field(0, ge=0)  # follow-ups sent since the candidate last wrote
    last_follow_up_at: AwareDatetime | None = None

    @property
    def waiting_since(self) -> datetime:
        return self.last_candidate_at or self.started_at


class SendFollowUp(_Frozen):
    action: Literal["follow_up"] = "follow_up"
    step: int  # 1-based
    kind: Literal["nudge", "last_call"]
    at: AwareDatetime
    requires_template: bool


class Abandon(_Frozen):
    action: Literal["abandon"] = "abandon"
    at: AwareDatetime


Planned = SendFollowUp | Abandon


def next_step(config: ReengagementConfig, silence: Silence, tz: ZoneInfo) -> Planned:
    """The next thing to do for this silence, and when; whether or not it is due yet."""
    steps = config.follow_ups
    sent = min(silence.steps_sent, len(steps))
    if sent == len(steps):
        last = silence.last_follow_up_at or silence.waiting_since + steps[-1].after
        return Abandon(at=last + config.abandon_after)
    step = steps[sent]
    at = silence.waiting_since + step.after
    if sent and silence.last_follow_up_at is not None:
        gap = step.after - steps[sent - 1].after
        at = max(at, silence.last_follow_up_at + gap)
    if config.quiet_hours is not None:
        at = postpone(at, tz, config.quiet_hours)
    opened = silence.last_candidate_at
    return SendFollowUp(
        step=sent + 1,
        kind=step.kind,
        at=at,
        requires_template=opened is None or at > opened + config.window,
    )


def due(
    config: ReengagementConfig, silence: Silence, tz: ZoneInfo, now: datetime
) -> Planned | None:
    """`next_step` if its time has come, else None."""
    planned = next_step(config, silence, tz)
    return planned if planned.at <= now else None


def postpone(at: datetime, tz: ZoneInfo, quiet: QuietHours) -> datetime:
    """Inside quiet hours -> the end of that quiet period, local time; else unchanged."""
    local = at.astimezone(tz)
    if not quiet.contains(local.time()):
        return at
    end = datetime.combine(local.date(), quiet.end, tzinfo=tz)
    if end <= local:  # 23:30 with quiet hours 22:00-09:00: the end is tomorrow
        end = datetime.combine(local.date() + timedelta(days=1), quiet.end, tzinfo=tz)
    return end.astimezone(UTC)
