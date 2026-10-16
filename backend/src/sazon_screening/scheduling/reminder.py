"""When the day-before interview reminder is due (spec 010 FR-6): pure time maths.

- planned for the day before the interview, at the configured local time (18:00);
- inside quiet hours -> postponed to their end, local time (as the follow-ups, spec 008),
  and never sent while they last (a tick that missed 18:00 waits until they end);
- never after the interview has started;
- not at all if the interview was booked after the planned time (e.g. at 20:00 for
  tomorrow 10:00): the confirmation was minutes ago, a reminder would only be noise.
"Once per booking" is the caller's compare-and-set on `reminder_sent_at`.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sazon_screening.reengagement import QuietHours, postpone
from sazon_screening.scheduling.config import ReminderConfig


def planned_reminder(starts_at: datetime, tz: ZoneInfo, at: time) -> datetime:
    """The day before the interview (local), at `at` (local); aware."""
    day_before = starts_at.astimezone(tz).date() - timedelta(days=1)
    return datetime.combine(day_before, at, tzinfo=tz)


def reminder_due(
    *,
    starts_at: datetime,
    booked_at: datetime,
    now: datetime,
    tz: ZoneInfo,
    config: ReminderConfig,
    quiet_hours: QuietHours | None,
) -> bool:
    if not config.enabled:
        return False
    planned = planned_reminder(starts_at, tz, config.at)
    if booked_at >= planned:
        return False
    if quiet_hours is None:
        return planned <= now < starts_at
    if quiet_hours.contains(now.astimezone(tz).time()):
        return False
    return postpone(planned, tz, quiet_hours) <= now < starts_at
