"""The "Zonas" page (spec 015 FR-7): staffing per served area, editable by recruiters.

Areas come from service_areas.yaml (a zone, or a city served as a whole); numbers come
from the `zone_staffing` table. An area without a row has no data: it is listed with
nulls, so a recruiter can fill it in.
"""

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from sazon_screening.api import repo
from sazon_screening.api.deps import ServiceDep, SessionDep
from sazon_screening.api.models import ZoneStaffing
from sazon_screening.api.schemas import ZoneOut, ZonePatchIn, ZonePipeline
from sazon_screening.api.staffing import PIPELINE_STATUSES, occupancy_pct, occupancy_ratio
from sazon_screening.config import EngineConfig
from sazon_screening.vocab import Country, Language, Status

router = APIRouter(prefix="/api/zones", tags=["recruiter dashboard"])


@dataclass(frozen=True)
class _Area:
    id: str
    name: str
    city: str
    city_name: str
    country: Country


def served_areas(config: EngineConfig, language: Language) -> Iterator[_Area]:
    """Every served area in config order, with display names in `language`."""
    for country in config.service_areas.countries:
        for city in country.cities:
            city_name = city.names[language]
            if not city.zones:
                yield _Area(city.id, city_name, city.id, city_name, country.id)
            for zone in city.zones:
                yield _Area(zone.id, zone.names[language], city.id, city_name, country.id)


@router.get("")
async def list_zones(
    session: SessionDep, service: ServiceDep, lang: Language = Language.es
) -> list[ZoneOut]:
    rows = {row.area_id: row for row in await repo.list_staffing(session)}
    pipeline = await _pipeline(session)
    return [
        _zone_out(area, rows.get(area.id), pipeline)
        for area in served_areas(service.engine_config, lang)
    ]


@router.patch("/{area_id}")
async def update_zone(
    area_id: str,
    body: ZonePatchIn,
    session: SessionDep,
    service: ServiceDep,
    lang: Language = Language.es,
) -> ZoneOut:
    """Set target and/or current drivers (each >= 0, else 422). Unknown area -> 404."""
    area = next((a for a in served_areas(service.engine_config, lang) if a.id == area_id), None)
    if area is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    now = service.now()
    row = await repo.get_staffing(session, area_id)
    if row is None:
        row = ZoneStaffing(area_id=area_id, target_drivers=0, current_drivers=0, updated_at=now)
        repo.add(session, row)
    if body.target_drivers is not None:
        row.target_drivers = body.target_drivers
    if body.current_drivers is not None:
        row.current_drivers = body.current_drivers
    row.updated_at = now
    await session.commit()
    return _zone_out(area, row, await _pipeline(session))


async def _pipeline(session: AsyncSession) -> Counter[tuple[str, Status]]:
    """(area id, status) -> qualified candidates; the area is the zone, else the city."""
    counts: Counter[tuple[str, Status]] = Counter()
    for city, zone, status, n in await repo.count_by_area_and_status(session, PIPELINE_STATUSES):
        area_id = zone or city
        if area_id is not None:
            counts[(area_id, Status(status))] += n
    return counts


def _zone_out(
    area: _Area, row: ZoneStaffing | None, pipeline: Counter[tuple[str, Status]]
) -> ZoneOut:
    ratio = occupancy_ratio(row.target_drivers, row.current_drivers) if row else None
    updated_at: datetime | None = row.updated_at if row else None
    return ZoneOut(
        id=area.id,
        name=area.name,
        city=area.city,
        city_name=area.city_name,
        country=area.country,
        target_drivers=row.target_drivers if row else None,
        current_drivers=row.current_drivers if row else None,
        occupancy_pct=occupancy_pct(ratio) if ratio is not None else None,
        full=ratio is not None and ratio >= 1.0,
        pipeline=ZonePipeline(
            qualified_unscheduled=pipeline[(area.id, Status.qualified_unscheduled)],
            interview_scheduled=pipeline[(area.id, Status.interview_scheduled)],
            waitlisted=pipeline[(area.id, Status.waitlisted)],
        ),
        updated_at=updated_at,
    )
