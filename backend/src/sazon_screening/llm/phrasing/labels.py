"""Human labels for ids: areas now; enum labels from the message catalog arrive in T17."""

from sazon_screening.config import EngineConfig
from sazon_screening.vocab import Language


def area_label(area_id: str, config: EngineConfig, language: Language) -> str:
    """A zone reads "Coyoacán (Ciudad de México)", a city "Madrid", an unknown id itself.

    The city is part of a zone's label because zone names repeat across cities
    ("Centro", "El Carmen"): it is exactly what the candidate must choose between.
    """
    for country in config.service_areas.countries:
        for city in country.cities:
            city_name = city.names[language]
            if city.id == area_id:
                return city_name
            for zone in city.zones:
                if zone.id == area_id:
                    return f"{zone.names[language]} ({city_name})"
    return area_id
