"""Interview slots on offer, from the recruiters' own agenda (spec 010 FR-1..3).

The service asks this provider which slots to send with a turn: generated from the
city's availability (the `interview_availability` table), minus slots already at
capacity. The maths is pure (`sazon_screening.scheduling`); this module only reads the
database and knows the timezones. Booking itself (the capacity check under a unique
index) is in `repo.book_seat`, inside the turn's transaction.
"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from sazon_screening.api import repo
from sazon_screening.api.models import InterviewAvailability
from sazon_screening.config.models import ServiceAreasConfig
from sazon_screening.llm.slots import SlotDisplay
from sazon_screening.scheduling import (
    AvailabilitySettings,
    InterviewConfig,
    SlotTime,
    city_timezone,
    display,
    load_interview_config,
    offer,
    parse_slot_id,
)


class SlotProvider:
    def __init__(self, config: InterviewConfig, service_areas: ServiceAreasConfig) -> None:
        self._config = config
        self._areas = service_areas

    @property
    def config(self) -> InterviewConfig:
        return self._config

    def timezone(self, city: str) -> ZoneInfo | None:
        return city_timezone(self._areas, city)

    async def init_availability(self, session: AsyncSession, now: datetime) -> list[str]:
        """FR-1: seed every configured city that has no availability yet; never overwrite
        what recruiters edited. Returns the cities it inserted."""
        existing = {row.city for row in await repo.list_availability(session)}
        added = [city for city in self._config.cities if city not in existing]
        for city in added:
            repo.add(session, availability_row(city, self._config.availability(city), now))
        return added

    async def offer(self, session: AsyncSession, city: str, now: datetime) -> list[SlotDisplay]:
        """FR-2: the slots to offer a candidate in `city` now (none for an unknown city)."""
        row = await repo.get_availability(session, city)
        tz = self.timezone(city)
        if row is None or tz is None:
            return []
        settings = settings_of(row)
        taken = await repo.seats_taken_by_slot(session, city, since=now)
        chosen = offer(city, settings, tz, now, taken, self._config.max_slots)
        return [display(slot, settings.place) for slot in chosen]

    async def describe(self, session: AsyncSession, slot_ids: list[str]) -> list[SlotDisplay]:
        """Labels (and place) for slots offered or booked earlier, full or not."""
        shown: list[SlotDisplay] = []
        places: dict[str, str | None] = {}
        for slot_id in dict.fromkeys(slot_ids):
            slot = parse_slot_id(slot_id)
            if slot is None:
                continue
            if slot.city not in places:
                row = await repo.get_availability(session, slot.city)
                places[slot.city] = row.place if row else None
            shown.append(display(slot, places[slot.city]))
        return shown

    def preview(self, city: str, now: datetime) -> list[SlotDisplay]:
        """The offer from the YAML alone, nothing booked: for evals and scripts (no DB)."""
        tz = self.timezone(city)
        if city not in self._config.cities or tz is None:
            return []
        settings = self._config.availability(city)
        chosen = offer(city, settings, tz, now, {}, self._config.max_slots)
        return [display(slot, settings.place) for slot in chosen]

    def starts_at(self, slot: SlotTime) -> datetime | None:
        tz = self.timezone(slot.city)
        return slot.starts_at(tz) if tz else None


def settings_of(row: InterviewAvailability) -> AvailabilitySettings:
    return AvailabilitySettings.model_validate(
        {
            "weekdays": row.weekdays_json,
            "times": row.times_json,
            "capacity": row.capacity,
            "duration_min": row.duration_min,
            "days_ahead": row.days_ahead,
            "place": row.place,
        }
    )


def availability_row(
    city: str, settings: AvailabilitySettings, now: datetime
) -> InterviewAvailability:
    row = InterviewAvailability(city=city, updated_at=now)
    apply_settings(row, settings, now)
    return row


def apply_settings(
    row: InterviewAvailability, settings: AvailabilitySettings, now: datetime
) -> None:
    row.weekdays_json = [day.value for day in settings.weekdays]
    row.times_json = list(settings.times)
    row.capacity = settings.capacity
    row.duration_min = settings.duration_min
    row.days_ahead = settings.days_ahead
    row.place = settings.place
    row.updated_at = now


def load_slot_provider(config_dir: Path, service_areas: ServiceAreasConfig) -> SlotProvider:
    return SlotProvider(load_interview_config(config_dir, service_areas), service_areas)
