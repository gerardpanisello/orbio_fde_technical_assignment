"""Display labels for config ids (cities, zones), so the dashboard never duplicates the YAML."""

from fastapi import APIRouter

from sazon_screening.api.deps import ServiceDep
from sazon_screening.api.schemas import AreaLabels
from sazon_screening.vocab import Language

router = APIRouter(prefix="/api/meta", tags=["recruiter dashboard"])


@router.get("/areas")
async def area_labels(service: ServiceDep, lang: Language = Language.es) -> AreaLabels:
    """`{cities: {madrid: "Madrid"}, zones: {mad-chamberi: "Chamberí"}}` from service_areas.yaml."""
    cities: dict[str, str] = {}
    zones: dict[str, str] = {}
    for country in service.engine_config.service_areas.countries:
        for city in country.cities:
            cities[city.id] = city.names[lang]
            for zone in city.zones:
                zones[zone.id] = zone.names[lang]
    return AreaLabels(cities=cities, zones=zones)
