"""Spec 015 T2: the staffing seed (zone_staffing.yaml) and the zone-demand bands."""

import shutil
from pathlib import Path

import pytest

from sazon_screening.config import ConfigError, load_config, load_zone_staffing
from sazon_screening.config.models import ServiceAreasConfig
from tests.paths import FIXTURE_CONFIG_DIR, SHIPPED_CONFIG_DIR


def occupancy(target: int, current: int) -> float:
    return current / target


@pytest.fixture(scope="module")
def staffing() -> dict[str, tuple[int, int]]:
    config = load_config(SHIPPED_CONFIG_DIR)
    seed = load_zone_staffing(SHIPPED_CONFIG_DIR, config.service_areas)
    return {k: (v.target_drivers, v.current_drivers) for k, v in seed.areas.items()}


class TestShipped:
    def test_salamanca_is_full_for_the_waitlist_demo(
        self, staffing: dict[str, tuple[int, int]]
    ) -> None:
        assert occupancy(*staffing["mad-salamanca"]) >= 1.0

    def test_demo_has_variety(self, staffing: dict[str, tuple[int, int]]) -> None:
        ratios = [occupancy(t, c) for t, c in staffing.values()]
        assert any(r < 0.5 for r in ratios)
        assert any(0.5 <= r < 0.8 for r in ratios)
        assert any(0.8 <= r < 1.0 for r in ratios)

    def test_seed_persona_places_have_room(self, staffing: dict[str, tuple[int, int]]) -> None:
        # The demo seed books interviews in these areas: they must not be full.
        seeded = ["mad-chamberi", "bcn-eixample", "val-ruzafa", "sev-triana", "mlg-teatinos"]
        seeded += ["cdmx-coyoacan", "gdl-providencia", "mty-san-pedro"]
        for area in seeded:
            assert occupancy(*staffing[area]) < 1.0, area

    def test_screening_has_zone_demand_bands(self) -> None:
        scoring = load_config(SHIPPED_CONFIG_DIR).screening.scoring
        assert [band.below_pct for band in scoring.zone_demand] == [50, 80, 100]
        assert scoring.max_score == 120
        assert 0 < scoring.buckets.medium < scoring.buckets.high <= scoring.max_score


@pytest.fixture
def areas() -> ServiceAreasConfig:
    return load_config(FIXTURE_CONFIG_DIR).service_areas


def write_seed(tmp_path: Path, body: str) -> Path:
    (tmp_path / "zone_staffing.yaml").write_text(f'version: "t"\n{body}', encoding="utf-8")
    return tmp_path


def test_valid_seed_loads(tmp_path: Path, areas: ServiceAreasConfig) -> None:
    seed = "areas:\n  mad-salamanca: {target_drivers: 30, current_drivers: 31}\n"
    staffing = load_zone_staffing(write_seed(tmp_path, seed), areas)
    assert staffing.areas["mad-salamanca"].current_drivers == 31


def test_empty_seed_means_no_data(tmp_path: Path, areas: ServiceAreasConfig) -> None:
    assert load_zone_staffing(write_seed(tmp_path, ""), areas).areas == {}


@pytest.mark.parametrize(
    ("area_id", "why"),
    [("mad-vallecas", "not served"), ("madrid", "a city with zones is not an area")],
)
def test_unknown_area_is_rejected_naming_it(
    tmp_path: Path, areas: ServiceAreasConfig, area_id: str, why: str
) -> None:
    seed = f"areas:\n  {area_id}: {{target_drivers: 3, current_drivers: 1}}\n"
    with pytest.raises(ConfigError, match=rf"zone_staffing.yaml: areas.{area_id}: not a served"):
        load_zone_staffing(write_seed(tmp_path, seed), areas)


def test_negative_numbers_are_rejected(tmp_path: Path, areas: ServiceAreasConfig) -> None:
    seed = "areas:\n  mad-salamanca: {target_drivers: 30, current_drivers: -1}\n"
    with pytest.raises(ConfigError, match=r"zone_staffing.yaml: areas.mad-salamanca.current"):
        load_zone_staffing(write_seed(tmp_path, seed), areas)


def test_missing_file_is_reported(tmp_path: Path, areas: ServiceAreasConfig) -> None:
    with pytest.raises(ConfigError, match=r"zone_staffing.yaml: file not found"):
        load_zone_staffing(tmp_path, areas)


def test_city_served_as_a_whole_is_an_area(tmp_path: Path) -> None:
    shutil.copy(FIXTURE_CONFIG_DIR / "screening.yaml", tmp_path / "screening.yaml")
    (tmp_path / "service_areas.yaml").write_text(
        'version: "t"\ncountries:\n  - id: ES\n    names: {es: España, en: Spain}\n'
        "    cities:\n      - id: toledo\n        names: {es: Toledo, en: Toledo}\n"
        "        timezone: Europe/Madrid\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    seed = "areas:\n  toledo: {target_drivers: 10, current_drivers: 2}\n"
    assert "toledo" in load_zone_staffing(write_seed(tmp_path, seed), config.service_areas).areas
