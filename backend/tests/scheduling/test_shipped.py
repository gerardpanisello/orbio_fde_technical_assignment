"""Spec 010: the shipped interview_slots.yaml loads and covers every served city."""

from pathlib import Path

import pytest

from sazon_screening.config import ConfigError, EngineConfig
from sazon_screening.scheduling import load_interview_config
from tests.paths import SHIPPED_CONFIG_DIR


def test_shipped_config_covers_every_served_city(shipped_config: EngineConfig) -> None:
    config = load_interview_config(SHIPPED_CONFIG_DIR, shipped_config.service_areas)
    served = {c.id for country in shipped_config.service_areas.countries for c in country.cities}
    assert set(config.cities) == served
    assert config.max_slots == 3
    for city in served:
        assert "ficticia" in config.availability(city).place or "ejemplo" in (
            config.availability(city).place
        )


def test_unknown_city_fails_at_load(tmp_path: Path, shipped_config: EngineConfig) -> None:
    (tmp_path / "interview_slots.yaml").write_text(
        'version: "t"\ncities:\n  atlantis: {weekdays: [mon], times: ["10:00"], capacity: 1,'
        " duration_min: 30, days_ahead: 1, place: X}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="atlantis"):
        load_interview_config(tmp_path, shipped_config.service_areas)
