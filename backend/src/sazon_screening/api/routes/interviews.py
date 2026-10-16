"""Interviews (spec 010): the candidate's calendar invite, and the recruiters' agenda.

- `GET  /api/interviews/{conversation_id}.ics`   the booked interview as an invite (FR-5)
- `GET  /api/interviews/availability`            every city's agenda (FR-1)
- `PATCH /api/interviews/availability/{city}`    edit it; only new offers change (AC-7)
- `GET  /api/interviews/week?city=&start=`       a week per city: capacity, who is booked (FR-7)
- `PATCH /api/interviews/bookings/{booking_id}`  attended / no-show (FR-7, AC-8)
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from sazon_screening.api import repo
from sazon_screening.api.deps import ServiceDep, SessionDep
from sazon_screening.api.models import SEAT_HOLDING, InterviewAvailability, InterviewBooking
from sazon_screening.api.schemas import (
    AttendanceIn,
    AvailabilityOut,
    AvailabilityPatchIn,
    BookingOut,
    WeekBookingOut,
    WeekDayOut,
    WeekOut,
    WeekSlotOut,
)
from sazon_screening.api.slots import apply_settings, availability_row, settings_of
from sazon_screening.config import EngineConfig
from sazon_screening.scheduling import AvailabilitySettings, SlotTime, parse_slot_id, week_start
from sazon_screening.vocab import Country, Language, Weekday

router = APIRouter(prefix="/api/interviews", tags=["interviews"])
_WEEKDAYS = list(Weekday)


@dataclass(frozen=True)
class _City:
    id: str
    name: str
    country: Country


def _cities(config: EngineConfig, language: Language) -> Iterator[_City]:
    for country in config.service_areas.countries:
        for city in country.cities:
            yield _City(city.id, city.names[language], country.id)


def _city(config: EngineConfig, city_id: str, language: Language) -> _City:
    found = next((c for c in _cities(config, language) if c.id == city_id), None)
    if found is None:
        raise HTTPException(status_code=404, detail="City not found")
    return found


# --- the invite --------------------------------------------------------------------------


@router.get(
    "/{conversation_id}.ics",
    response_class=Response,
    responses={200: {"content": {"text/calendar": {}}}, 404: {"description": "No interview"}},
)
async def interview_ics(conversation_id: str, service: ServiceDep) -> Response:
    """FR-5: the booked interview as an iCalendar invite (candidate and recruiter). 404 when
    the conversation does not exist or has no booked interview."""
    ics = await service.interview_ics(conversation_id)
    if ics is None:
        raise HTTPException(status_code=404, detail="No booked interview")
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="entrevista-grupo-sazon.ics"'},
    )


# --- availability ------------------------------------------------------------------------


@router.get("/availability")
async def list_availability(
    session: SessionDep, service: ServiceDep, lang: Language = Language.es
) -> list[AvailabilityOut]:
    """Every served city with an agenda, in service_areas.yaml order."""
    rows = {row.city: row for row in await repo.list_availability(session)}
    return [
        _availability_out(city, rows[city.id], service.timezone_name(city.id))
        for city in _cities(service.engine_config, lang)
        if city.id in rows
    ]


@router.patch("/availability/{city_id}")
async def update_availability(
    city_id: str,
    body: AvailabilityPatchIn,
    session: SessionDep,
    service: ServiceDep,
    lang: Language = Language.es,
) -> AvailabilityOut:
    """AC-7: validated as a whole (times HH:MM, capacity >= 1, ...; else 422). Bookings
    already made keep their slot; only slots offered from now on change. A served city
    without an agenda yet starts from the config defaults."""
    city = _city(service.engine_config, city_id, lang)
    row = await repo.get_availability(session, city_id)
    base = settings_of(row).model_dump() if row else service.slots.config.defaults.over({})
    try:
        settings = AvailabilitySettings.model_validate(body.over(base))
    except ValidationError as error:
        raise RequestValidationError(
            error.errors(include_url=False, include_context=False)
        ) from None
    now = service.now()
    if row is None:
        row = availability_row(city_id, settings, now)
        repo.add(session, row)
    else:
        apply_settings(row, settings, now)
    await session.commit()
    return _availability_out(city, row, service.timezone_name(city_id))


def _availability_out(city: _City, row: InterviewAvailability, timezone: str) -> AvailabilityOut:
    settings = settings_of(row)
    return AvailabilityOut(
        city=city.id,
        city_name=city.name,
        country=city.country,
        timezone=timezone,
        weekdays=settings.weekdays,
        times=settings.times,
        capacity=settings.capacity,
        duration_min=settings.duration_min,
        days_ahead=settings.days_ahead,
        place=settings.place,
        updated_at=row.updated_at,
    )


# --- the week view -----------------------------------------------------------------------


@router.get("/week")
async def week(
    city: str,
    session: SessionDep,
    service: ServiceDep,
    start: date | None = None,
    lang: Language = Language.es,
) -> WeekOut:
    """FR-7: Monday to Sunday of the week containing `start` (default: this week, local),
    each agenda slot with its capacity and the candidates booked in it."""
    found = _city(service.engine_config, city, lang)
    tz = service.slots.timezone(city)
    assert tz is not None  # every served city has a timezone (service_areas.yaml)
    now = service.now()
    monday = start - timedelta(days=start.weekday()) if start else week_start(now, tz)
    begin = datetime.combine(monday, time(0), tzinfo=tz)
    row = await repo.get_availability(session, city)
    settings = settings_of(row) if row else None
    booked = await repo.bookings_between(session, city, begin, begin + timedelta(days=7))
    names = await repo.names_of(session, {b.conversation_id for b in booked})
    by_slot: dict[str, list[InterviewBooking]] = {}
    for booking in booked:
        by_slot.setdefault(booking.slot_id, []).append(booking)
    days = []
    for offset in range(7):
        day = monday + timedelta(days=offset)
        weekday = _WEEKDAYS[day.weekday()]
        agenda = settings.times if settings and weekday in settings.weekdays else []
        extra = [
            slot.time
            for slot_id in by_slot
            if (slot := parse_slot_id(slot_id)) is not None and slot.day == day
        ]
        slots = [
            _week_slot(
                SlotTime(day=day, time=at, city=city),
                tz,
                capacity=settings.capacity if settings else 0,
                in_agenda=at in agenda,
                bookings=by_slot.get(f"{city}:{day.isoformat()}T{at}", []),
                names=names,
                now=now,
            )
            for at in sorted({*agenda, *extra})
        ]
        days.append(WeekDayOut(date=day, weekday=weekday, slots=slots))
    return WeekOut(city=city, city_name=found.name, timezone=tz.key, start=monday, days=days)


def _week_slot(
    slot: SlotTime,
    tz: ZoneInfo,
    *,
    capacity: int,
    in_agenda: bool,
    bookings: list[InterviewBooking],
    names: dict[str, str | None],
    now: datetime,
) -> WeekSlotOut:
    starts_at = slot.starts_at(tz)
    return WeekSlotOut(
        slot_id=slot.id,
        time=slot.time,
        starts_at=starts_at,
        capacity=capacity,
        booked=len(bookings),
        in_agenda=in_agenda,
        past=starts_at <= now,
        bookings=[
            WeekBookingOut.model_validate(
                {
                    "booking_id": b.id,
                    "conversation_id": b.conversation_id,
                    "full_name": names.get(b.conversation_id),
                    "status": b.status,
                    "seat": b.seat,
                }
            )
            for b in bookings
        ],
    )


# --- attendance --------------------------------------------------------------------------


@router.patch("/bookings/{booking_id}")
async def mark_attendance(
    booking_id: int, body: AttendanceIn, session: SessionDep, service: ServiceDep
) -> BookingOut:
    """FR-7: attended / no-show (feeds analytics `show_up_rate`, AC-8); `booked` undoes it.
    409 for a cancelled or moved booking, or one that has not started yet."""
    booking = await repo.get_booking(session, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status not in SEAT_HOLDING:
        raise HTTPException(status_code=409, detail=f"The booking was {booking.status}")
    now = service.now()
    if body.status != "booked" and booking.starts_at > now:
        raise HTTPException(status_code=409, detail="The interview has not happened yet")
    booking.status = body.status
    booking.updated_at = now
    await session.commit()
    return BookingOut.of(booking, service.timezone_name(booking.city))
