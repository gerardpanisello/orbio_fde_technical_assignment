"""Interview scheduling (spec 010): availability, slot offer, capacity, reminders, .ics.

Everything here is pure (no clock, no I/O): the API passes `now`, the city's timezone and
what the database says (availability, seats taken). The engine only sees slot ids.
"""

from sazon_screening.scheduling.config import (
    AvailabilitySettings,
    InterviewConfig,
    PartialAvailability,
    ReminderConfig,
    load_interview_config,
)
from sazon_screening.scheduling.slots import (
    SlotTime,
    city_timezone,
    display,
    generate,
    offer,
    parse_slot_id,
    week_start,
)

__all__ = [
    "AvailabilitySettings",
    "InterviewConfig",
    "PartialAvailability",
    "ReminderConfig",
    "SlotTime",
    "city_timezone",
    "display",
    "generate",
    "load_interview_config",
    "offer",
    "parse_slot_id",
    "week_start",
]
