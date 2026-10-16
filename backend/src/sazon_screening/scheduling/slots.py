"""Which interview slots to offer (spec 010 FR-2): pure time and capacity maths.

No clock and no database: callers pass `now` (aware), the city's timezone, its
availability and how many seats each slot already has taken. Every rule is unit-tested
with exact datetimes (AC-1):
- days start tomorrow, local time, and only the availability's weekdays count;
- a slot at or before `now` is never offered (whatever the clock says);
- a slot with `taken >= capacity` is never offered;
- the short list (`max_slots`) is spread over the days, rotating the times, so it still
  covers mornings and afternoons; a full preferred time falls back to the next open one.

A slot id is `<city>:<YYYY-MM-DDTHH:MM>` (local time): stable, readable, and enough to
rebuild the slot, so ids stored in a conversation never need a lookup table.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sazon_screening.config.models import ServiceAreasConfig
from sazon_screening.llm.slots import SlotDisplay
from sazon_screening.scheduling.config import AvailabilitySettings
from sazon_screening.vocab import Language, Weekday

_ES_DAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_SLOT_ID = re.compile(r"^(?P<city>[a-z0-9-]+):(?P<day>\d{4}-\d{2}-\d{2})T(?P<time>\d{2}:\d{2})$")
_WEEKDAYS = list(Weekday)


@dataclass(frozen=True, order=True)
class SlotTime:
    """One interview slot: a city, a local day and a local time ("10:00")."""

    day: date
    time: str
    city: str

    @property
    def id(self) -> str:
        return f"{self.city}:{self.day.isoformat()}T{self.time}"

    @property
    def local(self) -> datetime:
        """Naive local date-time (the wall clock in the city)."""
        hour, minute = (int(part) for part in self.time.split(":"))
        return datetime(self.day.year, self.day.month, self.day.day, hour, minute)

    def starts_at(self, tz: ZoneInfo) -> datetime:
        """The absolute start (aware, UTC)."""
        return self.local.replace(tzinfo=tz).astimezone(UTC)


def parse_slot_id(slot_id: str) -> SlotTime | None:
    """The slot an id names, or None for anything that is not a slot id."""
    match = _SLOT_ID.match(slot_id)
    if match is None:
        return None
    try:
        day = date.fromisoformat(match["day"])
        hour, minute = (int(part) for part in match["time"].split(":"))
    except ValueError:
        return None
    if hour > 23 or minute > 59:
        return None
    return SlotTime(day=day, time=match["time"], city=match["city"])


def generate(
    city: str, availability: AvailabilitySettings, tz: ZoneInfo, now: datetime
) -> list[SlotTime]:
    """Every slot of the next `days_ahead` interview days, from tomorrow (local), in order."""
    today = now.astimezone(tz).date()
    weekdays = {_WEEKDAYS.index(day) for day in availability.weekdays}
    days: list[date] = []
    day = today
    while len(days) < availability.days_ahead:
        day += timedelta(days=1)
        if day.weekday() in weekdays:
            days.append(day)
    slots = [SlotTime(day=d, time=t, city=city) for d in days for t in sorted(availability.times)]
    return [slot for slot in slots if slot.starts_at(tz) > now]


def offer(
    city: str,
    availability: AvailabilitySettings,
    tz: ZoneInfo,
    now: datetime,
    taken: Mapping[str, int],
    max_slots: int | None,
) -> list[SlotTime]:
    """The slots to offer: open ones only, spread over days and times (FR-2)."""
    every = generate(city, availability, tz, now)
    open_slots = [s for s in every if taken.get(s.id, 0) < availability.capacity]
    if max_slots is None:
        return open_slots
    times = sorted(availability.times)
    days = sorted({slot.day for slot in every})
    by_day: dict[date, list[SlotTime]] = {}
    for slot in open_slots:
        by_day.setdefault(slot.day, []).append(slot)
    spread: list[SlotTime] = []
    for index, day in enumerate(days):  # the index runs over all days: a stable rotation
        options = by_day.get(day, [])
        if not options:
            continue
        preferred = times[index % len(times)]
        later = [s for s in options if s.time >= preferred]
        spread.append(later[0] if later else options[0])
    rest = [slot for slot in open_slots if slot not in spread]
    return sorted((spread + rest)[:max_slots])


def display(slot: SlotTime, place: str | None = None) -> SlotDisplay:
    """Labels for the chat ("martes 20/10, 10:00"), plus where the interview is."""
    day = slot.day
    return SlotDisplay(
        id=slot.id,
        labels={
            Language.es: f"{_ES_DAYS[day.weekday()]} {day:%d/%m}, {slot.time}",
            Language.en: f"{day:%a %d %b}, {slot.time}",
        },
        place=place,
    )


def city_timezone(service_areas: ServiceAreasConfig, city: str) -> ZoneInfo | None:
    """The city's IANA timezone from service_areas.yaml, or None for an unknown city."""
    for country in service_areas.countries:
        for area in country.cities:
            if area.id == city:
                return ZoneInfo(area.timezone)
    return None


def week_start(now: datetime, tz: ZoneInfo) -> date:
    """The Monday of the local week that contains `now`."""
    today = now.astimezone(tz).date()
    return today - timedelta(days=today.weekday())
