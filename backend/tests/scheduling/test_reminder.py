"""Spec 010 T5: when the day-before reminder is due (AC-6), with an injected `now`."""

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest

from sazon_screening.reengagement import QuietHours
from sazon_screening.scheduling import ReminderConfig
from sazon_screening.scheduling.reminder import planned_reminder, reminder_due

MADRID = ZoneInfo("Europe/Madrid")
CDMX = ZoneInfo("America/Mexico_City")
STARTS = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)  # Tue 20/10 10:00 in Madrid
BOOKED = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
QUIET = QuietHours(start=time(22, 0), end=time(9, 0))


def due(now: datetime, **overrides: object) -> bool:
    values: dict[str, object] = {
        "starts_at": STARTS,
        "booked_at": BOOKED,
        "now": now,
        "tz": MADRID,
        "config": ReminderConfig(at=time(18, 0)),
        "quiet_hours": QUIET,
    } | overrides
    return reminder_due(**values)  # type: ignore[arg-type]


def test_planned_for_the_day_before_at_the_local_hour() -> None:
    assert planned_reminder(STARTS, MADRID, time(18, 0)) == datetime(
        2026, 10, 19, 16, 0, tzinfo=UTC
    )
    mx_start = datetime(2026, 10, 20, 16, 0, tzinfo=UTC)  # 10:00 in Mexico City
    assert planned_reminder(mx_start, CDMX, time(18, 0)) == datetime(2026, 10, 20, 0, 0, tzinfo=UTC)


@pytest.mark.ac("010:AC-6")
def test_due_from_the_local_hour_the_day_before_until_the_interview() -> None:
    assert not due(datetime(2026, 10, 19, 15, 59, tzinfo=UTC))  # 17:59 in Madrid
    assert due(datetime(2026, 10, 19, 16, 0, tzinfo=UTC))  # 18:00
    assert due(datetime(2026, 10, 20, 7, 59, tzinfo=UTC))  # 09:59 the next day (late tick)
    assert not due(datetime(2026, 10, 20, 8, 0, tzinfo=UTC))  # the interview has started


@pytest.mark.ac("010:AC-6")
def test_quiet_hours_postpone_it() -> None:
    late = ReminderConfig(at=time(23, 0))  # inside 22:00-09:00
    assert not due(datetime(2026, 10, 19, 21, 0, tzinfo=UTC), config=late)  # 23:00 local
    assert not due(datetime(2026, 10, 20, 6, 59, tzinfo=UTC), config=late)  # 08:59
    assert due(datetime(2026, 10, 20, 7, 0, tzinfo=UTC), config=late)  # 09:00, before 10:00
    assert due(datetime(2026, 10, 19, 21, 0, tzinfo=UTC), config=late, quiet_hours=None)


@pytest.mark.ac("010:AC-6")
def test_a_missed_reminder_still_waits_for_the_end_of_quiet_hours() -> None:
    assert not due(datetime(2026, 10, 19, 21, 30, tzinfo=UTC))  # 23:30 local: quiet
    assert due(datetime(2026, 10, 20, 7, 0, tzinfo=UTC))  # 09:00 local, before 10:00


@pytest.mark.ac("010:AC-6")
def test_not_sent_when_booked_after_the_reminder_time() -> None:
    booked_late = datetime(2026, 10, 19, 18, 30, tzinfo=UTC)  # 20:30 the day before
    assert not due(datetime(2026, 10, 19, 19, 0, tzinfo=UTC), booked_at=booked_late)


def test_disabled_is_never_due() -> None:
    off = ReminderConfig(enabled=False, at=time(18, 0))
    assert not due(datetime(2026, 10, 19, 16, 0, tzinfo=UTC), config=off)
