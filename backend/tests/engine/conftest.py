"""Shared engine fixtures: the fixture config, its variants and the injected `today`."""

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from sazon_screening.config import EngineConfig, load_config
from tests.paths import FIXTURE_CONFIG_DIR

# Monday. AC-17 depends on this weekday.
TODAY = date(2026, 10, 12)

MakeConfig = Callable[..., EngineConfig]


def deep_update(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_update(merged[key], value)
        else:
            merged[key] = value
    return merged


@pytest.fixture(scope="session")
def config() -> EngineConfig:
    return load_config(FIXTURE_CONFIG_DIR)


@pytest.fixture(scope="session")
def make_config(config: EngineConfig) -> MakeConfig:
    """Return a factory: `make_config(screening={"thresholds": {"max_reasks": 1}})`.

    The variant is re-validated from scratch, so every config validator (and anything
    derived at validation time) applies exactly as it would to a real YAML file.
    """

    def make(**overrides: Any) -> EngineConfig:
        data = deep_update(config.model_dump(mode="json"), overrides)
        return EngineConfig.model_validate(data)

    return make


@pytest.fixture(scope="session")
def bike_free_config(make_config: MakeConfig) -> EngineConfig:
    """AC-8/AC-9 variant: bicycles do not need a license."""
    return make_config(screening={"license_required": {"bicycle": False}})


@pytest.fixture
def today() -> date:
    return TODAY
