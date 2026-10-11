"""T6: the client config in the repo-root config/ loads and keeps the demo cases."""

import pytest

from sazon_screening.config import EngineConfig, load_config
from sazon_screening.config.areas import normalise
from sazon_screening.vocab import Country, VehicleType
from tests.paths import SHIPPED_CONFIG_DIR


@pytest.fixture(scope="module")
def shipped() -> EngineConfig:
    return load_config(SHIPPED_CONFIG_DIR)


def all_ids(config: EngineConfig) -> set[str]:
    ids: set[str] = set()
    for country in config.service_areas.countries:
        for city in country.cities:
            ids |= {city.id, *(zone.id for zone in city.zones)}
    return ids


def cities_answering_to(config: EngineConfig, name: str) -> list[tuple[Country, str]]:
    """(country, city id) of every city with a zone whose name or alias matches `name`."""
    key = normalise(name)
    return [
        (country.id, city.id)
        for country in config.service_areas.countries
        for city in country.cities
        if any(key in zone.match_keys() for zone in city.zones)
    ]


def test_shipped_config_loads(shipped: EngineConfig) -> None:
    assert shipped.version


def test_contains_the_demo_places(shipped: EngineConfig) -> None:
    assert {"madrid", "cdmx", "cdmx-coyoacan"} <= all_ids(shipped)


@pytest.mark.parametrize(
    ("alias", "city_id"),
    [
        ("CDMX", "cdmx"),
        ("DF", "cdmx"),
        ("BCN", "barcelona"),
        ("MTY", "monterrey"),
        ("GDL", "guadalajara"),
    ],
)
def test_city_aliases(shipped: EngineConfig, alias: str, city_id: str) -> None:
    cities = {
        city.id: city for country in shipped.service_areas.countries for city in country.cities
    }
    assert normalise(alias) in cities[city_id].match_keys()


def test_el_carmen_is_in_two_countries(shipped: EngineConfig) -> None:
    # Deliberate ambiguity resolved by country_hint (AC-13).
    countries = {country for country, _ in cities_answering_to(shipped, "El Carmen")}
    assert countries == {Country.ES, Country.MX}


def test_centro_is_in_several_cities_of_one_country(shipped: EngineConfig) -> None:
    # Deliberate ambiguity that country_hint cannot resolve: the engine must confirm.
    spanish = [city for country, city in cities_answering_to(shipped, "Centro") if country == "ES"]
    assert len(spanish) >= 2


def test_chapultepec_is_ambiguous_between_cdmx_and_guadalajara(shipped: EngineConfig) -> None:
    # Bosque de Chapultepec (CDMX) vs colonia Chapultepec (GDL): never resolve silently.
    cities = {city for _, city in cities_answering_to(shipped, "Chapultepec")}
    assert cities == {"cdmx", "guadalajara"}


def test_all_platforms_present(shipped: EngineConfig) -> None:
    assert {p.id for p in shipped.screening.platforms} == {
        "glovo",
        "uber_eats",
        "just_eat",
        "deliveroo",
        "rappi",
        "didi_food",
        "amazon_flex",
    }


def test_license_rules_cover_every_vehicle(shipped: EngineConfig) -> None:
    assert set(shipped.screening.license_required) == {v.value for v in VehicleType}
