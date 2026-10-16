"""Spec 010 T1: availability validation (the logic behind AC-7) and the shipped YAML."""

import pytest
from pydantic import ValidationError

from sazon_screening.scheduling import (
    AvailabilitySettings,
    InterviewConfig,
    PartialAvailability,
)
from sazon_screening.vocab import Weekday

VALID: dict[str, object] = {
    "weekdays": ["mon", "wed"],
    "times": ["17:00", "10:00"],
    "capacity": 2,
    "duration_min": 30,
    "days_ahead": 3,
    "place": "Calle Falsa 123",
}


def test_settings_are_stored_sorted() -> None:
    parsed = AvailabilitySettings.model_validate(VALID | {"weekdays": ["fri", "mon"]})
    assert parsed.times == ["10:00", "17:00"]
    assert parsed.weekdays == [Weekday.mon, Weekday.fri]


@pytest.mark.ac("010:AC-7")
@pytest.mark.parametrize(
    "change",
    [
        {"times": ["9:00"]},
        {"times": ["24:00"]},
        {"times": ["10:60"]},
        {"times": ["10h"]},
        {"times": []},
        {"times": ["10:00", "10:00"]},
        {"capacity": 0},
        {"capacity": -1},
        {"weekdays": []},
        {"weekdays": ["monday"]},
        {"days_ahead": 0},
        {"duration_min": 0},
        {"place": "   "},
    ],
)
def test_invalid_settings_are_rejected(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AvailabilitySettings.model_validate(VALID | change)


def test_a_partial_change_applies_on_top() -> None:
    base = AvailabilitySettings.model_validate(VALID)
    patch = PartialAvailability(capacity=5)
    changed = AvailabilitySettings.model_validate(patch.over(base.model_dump()))
    assert changed.capacity == 5
    assert changed.times == base.times


def test_city_overrides_merge_with_the_defaults() -> None:
    config = InterviewConfig.model_validate(
        {
            "version": "t",
            "defaults": {k: v for k, v in VALID.items() if k != "place"},
            "cities": {"madrid": {"place": "Aquí", "capacity": 4}},
        }
    )
    madrid = config.availability("madrid")
    assert (madrid.capacity, madrid.place, madrid.days_ahead) == (4, "Aquí", 3)


def test_a_city_without_a_place_fails_naming_the_city() -> None:
    with pytest.raises(ValidationError, match=r"cities\.madrid"):
        InterviewConfig.model_validate(
            {"version": "t", "defaults": VALID | {"place": None}, "cities": {"madrid": {}}}
        )
