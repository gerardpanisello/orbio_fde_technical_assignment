"""Spec 010 T1: slot generation and capacity maths (AC-1), with an injected `now`."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from sazon_screening.scheduling import (
    AvailabilitySettings,
    SlotTime,
    display,
    generate,
    offer,
    parse_slot_id,
    week_start,
)
from sazon_screening.vocab import Language, Weekday

MADRID = ZoneInfo("Europe/Madrid")
CDMX = ZoneInfo("America/Mexico_City")
WORKDAYS = [Weekday.mon, Weekday.tue, Weekday.wed, Weekday.thu, Weekday.fri]


def settings(**overrides: object) -> AvailabilitySettings:
    values: dict[str, object] = {
        "weekdays": WORKDAYS,
        "times": ["10:00", "17:00"],
        "capacity": 1,
        "duration_min": 30,
        "days_ahead": 3,
        "place": "Oficina",
    }
    return AvailabilitySettings.model_validate(values | overrides)


def ids(slots: list[SlotTime]) -> list[str]:
    return [slot.id for slot in slots]


@pytest.mark.ac("010:AC-1")
def test_generates_the_next_working_days_from_tomorrow_skipping_the_weekend() -> None:
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)  # Friday 14:00 in Madrid
    slots = generate("madrid", settings(), MADRID, now)
    assert ids(slots) == [
        "madrid:2026-10-19T10:00",
        "madrid:2026-10-19T17:00",
        "madrid:2026-10-20T10:00",
        "madrid:2026-10-20T17:00",
        "madrid:2026-10-21T10:00",
        "madrid:2026-10-21T17:00",
    ]


@pytest.mark.ac("010:AC-1")
def test_tomorrow_is_the_city_local_tomorrow() -> None:
    """23:30 UTC on Monday is already Tuesday in Madrid, still Monday in Mexico City."""
    now = datetime(2026, 10, 12, 23, 30, tzinfo=UTC)
    assert generate("madrid", settings(days_ahead=1), MADRID, now)[0].day == date(2026, 10, 14)
    assert generate("cdmx", settings(days_ahead=1), CDMX, now)[0].day == date(2026, 10, 13)


@pytest.mark.ac("010:AC-1")
def test_only_the_configured_weekdays_count() -> None:
    now = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)  # Monday
    slots = generate(
        "madrid", settings(weekdays=[Weekday.sat, Weekday.wed], times=["11:00"]), MADRID, now
    )
    assert ids(slots) == [
        "madrid:2026-10-14T11:00",
        "madrid:2026-10-17T11:00",
        "madrid:2026-10-21T11:00",
    ]


@pytest.mark.ac("010:AC-1")
def test_never_offers_a_past_time() -> None:
    """A slot at or before `now` is dropped, even with a clock in an odd timezone."""
    tomorrow_10 = datetime(2026, 10, 13, 8, 0, tzinfo=UTC)  # Tue 10:00 in Madrid
    slots = generate("madrid", settings(days_ahead=1), MADRID, tomorrow_10)
    assert ids(slots) == ["madrid:2026-10-14T10:00", "madrid:2026-10-14T17:00"]
    assert all(slot.starts_at(MADRID) > tomorrow_10 for slot in slots)


@pytest.mark.ac("010:AC-1")
def test_full_slots_are_never_offered() -> None:
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    taken = {"madrid:2026-10-19T10:00": 1, "madrid:2026-10-20T17:00": 2}
    every = offer("madrid", settings(), MADRID, now, taken, None)
    assert "madrid:2026-10-19T10:00" not in ids(every)
    assert "madrid:2026-10-20T17:00" not in ids(every)
    assert len(every) == 4
    with_room = offer("madrid", settings(capacity=2), MADRID, now, taken, None)
    assert "madrid:2026-10-19T10:00" in ids(with_room)  # 1 of 2 seats taken
    assert "madrid:2026-10-20T17:00" not in ids(with_room)


@pytest.mark.ac("010:AC-1")
def test_max_slots_spreads_over_days_rotating_times() -> None:
    now = datetime(2026, 10, 13, 8, 0, tzinfo=UTC)  # Tuesday
    slots = offer("madrid", settings(), MADRID, now, {}, 3)
    assert ids(slots) == [
        "madrid:2026-10-14T10:00",
        "madrid:2026-10-15T17:00",
        "madrid:2026-10-16T10:00",
    ]


@pytest.mark.ac("010:AC-1")
def test_a_full_preferred_time_falls_back_to_another_open_time_that_day() -> None:
    now = datetime(2026, 10, 13, 8, 0, tzinfo=UTC)
    taken = {"madrid:2026-10-15T17:00": 1}
    slots = offer("madrid", settings(), MADRID, now, taken, 3)
    assert ids(slots) == [
        "madrid:2026-10-14T10:00",
        "madrid:2026-10-15T10:00",
        "madrid:2026-10-16T10:00",
    ]


@pytest.mark.ac("010:AC-1")
def test_a_full_day_is_skipped_and_the_list_is_filled_from_the_rest() -> None:
    now = datetime(2026, 10, 13, 8, 0, tzinfo=UTC)
    taken = {"madrid:2026-10-15T10:00": 1, "madrid:2026-10-15T17:00": 1}
    slots = offer("madrid", settings(), MADRID, now, taken, 3)
    assert ids(slots) == [
        "madrid:2026-10-14T10:00",
        "madrid:2026-10-14T17:00",
        "madrid:2026-10-16T10:00",
    ]


@pytest.mark.ac("010:AC-1")
def test_everything_full_offers_nothing() -> None:
    now = datetime(2026, 10, 13, 8, 0, tzinfo=UTC)
    every = generate("madrid", settings(), MADRID, now)
    assert offer("madrid", settings(), MADRID, now, {s.id: 1 for s in every}, 3) == []


def test_starts_at_is_timezone_correct_in_both_countries() -> None:
    slot = SlotTime(day=date(2026, 10, 20), time="10:00", city="x")
    assert slot.starts_at(MADRID) == datetime(2026, 10, 20, 8, 0, tzinfo=UTC)  # CEST
    assert slot.starts_at(CDMX) == datetime(2026, 10, 20, 16, 0, tzinfo=UTC)  # CST, no DST
    winter = SlotTime(day=date(2026, 10, 26), time="10:00", city="x")
    assert winter.starts_at(MADRID) == datetime(2026, 10, 26, 9, 0, tzinfo=UTC)  # CET


def test_slot_ids_round_trip() -> None:
    slot = SlotTime(day=date(2026, 10, 20), time="17:00", city="cdmx")
    assert slot.id == "cdmx:2026-10-20T17:00"
    assert parse_slot_id(slot.id) == slot


@pytest.mark.parametrize(
    "bad", ["", "2026-10-20T10:00", "madrid:2026-13-01T10:00", "madrid:2026-10-20T25:00", "s1"]
)
def test_parse_rejects_what_is_not_a_slot_id(bad: str) -> None:
    assert parse_slot_id(bad) is None


def test_display_labels_and_place() -> None:
    shown = display(SlotTime(day=date(2026, 10, 20), time="10:00", city="madrid"), "Calle X")
    assert shown.label(Language.es) == "martes 20/10, 10:00"
    assert shown.label(Language.en) == "Tue 20 Oct, 10:00"
    assert shown.place == "Calle X"


def test_week_start_is_the_local_monday() -> None:
    sunday_night_utc = datetime(2026, 10, 18, 23, 0, tzinfo=UTC)  # Monday 01:00 in Madrid
    assert week_start(sunday_night_utc, MADRID) == date(2026, 10, 19)
    assert week_start(sunday_night_utc, CDMX) == date(2026, 10, 12)
