"""T1 of spec 008: the follow-up schedule as pure time maths, with exact datetimes."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from sazon_screening.config import load_config
from sazon_screening.reengagement import (
    Abandon,
    QuietHours,
    ReengagementConfig,
    SendFollowUp,
    Silence,
    due,
    load_reengagement,
    next_step,
    postpone,
    timezone_for,
)
from sazon_screening.vocab import Country
from tests.paths import SHIPPED_CONFIG_DIR

MADRID = ZoneInfo("Europe/Madrid")
MEXICO_CITY = ZoneInfo("America/Mexico_City")


@pytest.fixture(scope="module")
def config() -> ReengagementConfig:
    """The shipped schedule: 2 h, 23 h, 72 h, abandon 24 h later, quiet 22:00-09:00."""
    return load_reengagement(SHIPPED_CONFIG_DIR, load_config(SHIPPED_CONFIG_DIR).service_areas)


def local(tz: ZoneInfo, day: int, hour: int, minute: int = 0) -> datetime:
    """A local wall-clock time in October 2026 (Madrid is UTC+2 until the 25th)."""
    return datetime(2026, 10, day, hour, minute, tzinfo=tz)


def silence(
    last: datetime | None,
    *,
    steps: int = 0,
    last_follow_up: datetime | None = None,
    started: datetime | None = None,
) -> Silence:
    return Silence(
        started_at=started or last or local(MADRID, 12, 8),
        last_candidate_at=last,
        steps_sent=steps,
        last_follow_up_at=last_follow_up,
    )


def follow_up(planned: object) -> SendFollowUp:
    assert isinstance(planned, SendFollowUp), planned
    return planned


# --- AC-1: the schedule counts from the candidate's last message --------------------------


@pytest.mark.ac("008:AC-1")
def test_first_follow_up_is_due_two_hours_after_the_last_message(
    config: ReengagementConfig,
) -> None:
    quiet = silence(local(MADRID, 12, 10))
    planned = next_step(config, quiet, MADRID)
    assert planned == SendFollowUp(
        step=1, kind="nudge", at=local(MADRID, 12, 12), requires_template=False
    )
    assert due(config, quiet, MADRID, local(MADRID, 12, 11, 59)) is None  # nothing before
    assert due(config, quiet, MADRID, local(MADRID, 12, 12)) == planned


@pytest.mark.ac("008:AC-1")
def test_second_follow_up_is_23_hours_after_the_last_message(config: ReengagementConfig) -> None:
    quiet = silence(local(MADRID, 12, 10), steps=1, last_follow_up=local(MADRID, 12, 12))
    planned = follow_up(next_step(config, quiet, MADRID))
    assert (planned.step, planned.at) == (2, local(MADRID, 13, 9))  # 09:00: quiet hours over
    assert planned.requires_template is False  # 23 h < the 24 h window
    assert due(config, quiet, MADRID, local(MADRID, 13, 8, 59)) is None


@pytest.mark.ac("008:AC-1")
def test_a_late_previous_step_keeps_the_configured_gap(config: ReengagementConfig) -> None:
    """Step 1 went out a day late (downtime): step 2 waits its 21 h gap, not sent at once."""
    sent_late = local(MADRID, 13, 14)
    quiet = silence(local(MADRID, 12, 10), steps=1, last_follow_up=sent_late)
    assert next_step(config, quiet, MADRID).at == sent_late + timedelta(hours=21)


@pytest.mark.ac("008:AC-1")
def test_the_last_step_is_the_last_call(config: ReengagementConfig) -> None:
    quiet = silence(local(MADRID, 12, 10), steps=2, last_follow_up=local(MADRID, 13, 9))
    planned = follow_up(next_step(config, quiet, MADRID))
    assert (planned.step, planned.kind, planned.at) == (3, "last_call", local(MADRID, 15, 10))


# --- AC-2: quiet hours, in the candidate's own timezone ----------------------------------


@pytest.mark.ac("008:AC-2")
def test_a_follow_up_due_at_23_30_waits_until_09_00_local(config: ReengagementConfig) -> None:
    planned = next_step(config, silence(local(MADRID, 12, 21, 30)), MADRID)
    assert planned.at == local(MADRID, 13, 9)


@pytest.mark.ac("008:AC-2")
@pytest.mark.parametrize("tz", [MADRID, MEXICO_CITY], ids=["Madrid", "Mexico City"])
def test_each_city_uses_its_own_clock(config: ReengagementConfig, tz: ZoneInfo) -> None:
    """The same local times give the same local result, whatever the UTC offset."""
    planned = next_step(config, silence(local(tz, 12, 21, 30)), tz)
    assert planned.at.astimezone(tz) == local(tz, 13, 9)


@pytest.mark.ac("008:AC-2")
def test_the_same_instant_is_quiet_in_madrid_but_not_in_mexico(
    config: ReengagementConfig,
) -> None:
    """23:30 in Madrid is 15:30 in Mexico City: only Madrid waits."""
    last = local(MADRID, 12, 21, 30)
    assert next_step(config, silence(last), MADRID).at == local(MADRID, 13, 9)
    assert next_step(config, silence(last), MEXICO_CITY).at == last + timedelta(hours=2)


@pytest.mark.ac("008:AC-2")
@pytest.mark.parametrize(
    ("hour", "minute", "postponed"),
    [(21, 59, False), (22, 0, True), (2, 0, True), (8, 59, True), (9, 0, False), (15, 0, False)],
)
def test_quiet_hours_bounds(hour: int, minute: int, postponed: bool) -> None:
    quiet = QuietHours.model_validate({"start": "22:00", "end": "09:00"})
    at = local(MADRID, 12, hour, minute)
    result = postpone(at, MADRID, quiet)
    assert (result != at) is postponed
    if postponed:
        assert result.astimezone(MADRID).hour == 9
        assert result > at


def test_quiet_hours_that_do_not_wrap_midnight() -> None:
    quiet = QuietHours.model_validate({"start": "13:00", "end": "16:00"})
    assert postpone(local(MADRID, 12, 14), MADRID, quiet) == local(MADRID, 12, 16)
    assert postpone(local(MADRID, 12, 12), MADRID, quiet) == local(MADRID, 12, 12)


def test_quiet_hours_across_the_dst_change(config: ReengagementConfig) -> None:
    """25 Oct 2026: Madrid goes from UTC+2 to UTC+1. 09:00 local is still 09:00 local."""
    planned = next_step(config, silence(local(MADRID, 24, 22)), MADRID)
    assert planned.at.astimezone(MADRID) == local(MADRID, 25, 9)
    assert planned.at == datetime(2026, 10, 25, 8, 0, tzinfo=UTC)


# --- AC-3: the WhatsApp 24 h window -------------------------------------------------------


@pytest.mark.ac("008:AC-3")
def test_a_follow_up_past_the_window_must_be_a_template(config: ReengagementConfig) -> None:
    quiet = silence(local(MADRID, 12, 10), steps=2, last_follow_up=local(MADRID, 13, 9))
    assert follow_up(next_step(config, quiet, MADRID)).requires_template is True  # 72 h


@pytest.mark.ac("008:AC-3")
def test_postponing_past_the_window_makes_it_a_template(config: ReengagementConfig) -> None:
    """Step 2 is 23 h after the message. From 08:30 that is 07:30, quiet until 09:00:
    24.5 h after the message, past the window. From 10:00 it is 09:00, inside it."""
    early = local(MADRID, 12, 8, 30)
    planned = follow_up(next_step(config, silence(early, steps=1, last_follow_up=early), MADRID))
    assert (planned.at, planned.requires_template) == (local(MADRID, 13, 9), True)
    later = local(MADRID, 12, 10)
    planned = follow_up(next_step(config, silence(later, steps=1, last_follow_up=later), MADRID))
    assert (planned.at, planned.requires_template) == (local(MADRID, 13, 9), False)


@pytest.mark.ac("008:AC-3")
def test_a_candidate_who_never_wrote_only_gets_templates(config: ReengagementConfig) -> None:
    planned = follow_up(next_step(config, silence(None, started=local(MADRID, 12, 10)), MADRID))
    assert (planned.at, planned.requires_template) == (local(MADRID, 12, 12), True)


# --- AC-4: abandon after the last follow-up -----------------------------------------------


@pytest.mark.ac("008:AC-4")
def test_abandon_is_due_after_the_last_follow_up(config: ReengagementConfig) -> None:
    sent = local(MADRID, 15, 10)
    quiet = silence(local(MADRID, 12, 10), steps=3, last_follow_up=sent)
    abandon = Abandon(at=sent + timedelta(hours=24))
    assert next_step(config, quiet, MADRID) == abandon
    assert due(config, quiet, MADRID, sent + timedelta(hours=23, minutes=59)) is None
    assert due(config, quiet, MADRID, sent + timedelta(hours=24)) == abandon


@pytest.mark.ac("008:AC-4")
def test_abandon_ignores_quiet_hours(config: ReengagementConfig) -> None:
    """No message is sent, so the time of day does not matter."""
    sent = local(MADRID, 14, 23)
    quiet = silence(local(MADRID, 12, 10), steps=3, last_follow_up=sent)
    assert next_step(config, quiet, MADRID).at == local(MADRID, 15, 23)


# --- demo time and timezones --------------------------------------------------------------


def test_time_scale_shrinks_every_duration_and_drops_quiet_hours(
    config: ReengagementConfig,
) -> None:
    fast = config.scaled(60)  # an hour in a minute
    last = local(MADRID, 12, 21, 30)
    assert next_step(fast, silence(last), MADRID).at == last + timedelta(minutes=2)
    assert fast.abandon_after == timedelta(minutes=24)
    assert fast.window == timedelta(minutes=24)
    assert config.scaled(1) is config


def test_timezone_is_the_city_then_the_country_default(config: ReengagementConfig) -> None:
    areas = load_config(SHIPPED_CONFIG_DIR).service_areas
    city = areas.countries[1].cities[0]

    def tz(city_id: str | None, country: Country | None) -> ZoneInfo:
        return timezone_for(
            config, areas, city_id=city_id, country=country, default_country=Country.ES
        )

    assert str(tz(city.id, None)) == city.timezone
    assert tz(None, Country.MX) == MEXICO_CITY
    assert tz(None, None) == MADRID
