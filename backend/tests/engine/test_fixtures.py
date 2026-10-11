"""T5: the config variants used by AC tests are what they claim to be."""

from sazon_screening.config import EngineConfig
from sazon_screening.engine.enums import VehicleType
from tests.engine.conftest import MakeConfig


def test_bike_free_config_only_frees_bicycles(
    config: EngineConfig, bike_free_config: EngineConfig
) -> None:
    assert config.screening.requires_license(VehicleType.bicycle)
    assert not bike_free_config.screening.requires_license(VehicleType.bicycle)
    assert bike_free_config.screening.requires_license(VehicleType.motorbike)


def test_make_config_deep_updates_one_value(config: EngineConfig, make_config: MakeConfig) -> None:
    variant = make_config(screening={"thresholds": {"fuzzy_match_min_score": 95}})
    assert variant.thresholds.fuzzy_match_min_score == 95
    assert variant.thresholds.max_reasks == config.thresholds.max_reasks
    assert variant.service_areas == config.service_areas
