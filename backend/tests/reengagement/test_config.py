"""Spec 008 FR-1: `reengagement.yaml` is validated at startup with a clear error."""

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from sazon_screening.config import ConfigError, load_config
from sazon_screening.config.models import ServiceAreasConfig
from sazon_screening.reengagement import load_reengagement
from tests.paths import SHIPPED_CONFIG_DIR

VALID: dict[str, Any] = {
    "version": "test",
    "follow_ups": [{"after": "2h", "kind": "nudge"}, {"after": "3d", "kind": "last_call"}],
    "abandon_after": "24h",
    "quiet_hours": {"start": "22:00", "end": "09:00"},
    "default_timezones": {"ES": "Europe/Madrid", "MX": "America/Mexico_City"},
}


@pytest.fixture(scope="module")
def areas() -> ServiceAreasConfig:
    return load_config(SHIPPED_CONFIG_DIR).service_areas


def write(tmp_path: Path, data: dict[str, Any]) -> Path:
    (tmp_path / "reengagement.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    return tmp_path


def test_the_shipped_schedule_is_the_suggested_one(areas: ServiceAreasConfig) -> None:
    config = load_reengagement(SHIPPED_CONFIG_DIR, areas)
    assert [step.after for step in config.follow_ups] == [
        timedelta(hours=2),
        timedelta(hours=23),
        timedelta(hours=72),
    ]
    assert config.abandon_after == timedelta(hours=24)
    assert config.enabled


def test_durations_in_minutes_days_and_seconds(tmp_path: Path, areas: ServiceAreasConfig) -> None:
    data = VALID | {
        "follow_ups": [{"after": "30m", "kind": "nudge"}, {"after": "1.5d", "kind": "last_call"}],
        "abandon_after": "90s",
    }
    config = load_reengagement(write(tmp_path, data), areas)
    assert config.follow_ups[1].after == timedelta(hours=36)
    assert config.abandon_after == timedelta(seconds=90)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"abandon_after": "soon"}, "not a duration"),
        (
            {
                "follow_ups": [
                    {"after": "5h", "kind": "nudge"},
                    {"after": "2h", "kind": "last_call"},
                ]
            },
            "strictly increasing",
        ),
        ({"follow_ups": [{"after": "2h", "kind": "nudge"}]}, "last_call"),
        ({"follow_ups": []}, "follow_ups"),
        ({"quiet_hours": {"start": "22:00", "end": "22:00"}}, "same time"),
        ({"default_timezones": {"ES": "Europe/Madird", "MX": "America/Mexico_City"}}, "Madird"),
        ({"default_timezones": {"ES": "Europe/Madrid"}}, "missing MX"),
        ({"surprise": 1}, "surprise"),
    ],
)
def test_a_bad_file_fails_at_startup_naming_the_problem(
    tmp_path: Path, areas: ServiceAreasConfig, change: dict[str, Any], message: str
) -> None:
    with pytest.raises(ConfigError, match=r"reengagement\.yaml") as error:
        load_reengagement(write(tmp_path, VALID | change), areas)
    assert message in str(error.value)
