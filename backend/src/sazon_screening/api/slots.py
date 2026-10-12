"""Interview slots on offer (FR-5): the next working days at fixed times, from config.

Slot ids are ISO local date-times ("2026-10-13T10:00"), so a booked slot is readable as
it is stored. Real calendars replace this in spec 010.
"""

from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from sazon_screening.config import load_yaml_model
from sazon_screening.llm.slots import SlotDisplay
from sazon_screening.vocab import Language

SLOTS_FILE = "interview_slots.yaml"
_ES_DAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
Time = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class SlotConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    working_days: int = Field(gt=0, le=10)
    times: list[Time] = Field(min_length=1)


class SlotProvider:
    def __init__(self, config: SlotConfig) -> None:
        self._config = config

    def slots(self, today: date) -> list[SlotDisplay]:
        return [_slot(day, time) for day in self._days(today) for time in self._config.times]

    def _days(self, today: date) -> list[date]:
        days: list[date] = []
        day = today
        while len(days) < self._config.working_days:
            day += timedelta(days=1)
            if day.weekday() < 5:
                days.append(day)
        return days


def _slot(day: date, time: str) -> SlotDisplay:
    return SlotDisplay(
        id=f"{day.isoformat()}T{time}",
        labels={
            Language.es: f"{_ES_DAYS[day.weekday()]} {day:%d/%m}, {time}",
            Language.en: f"{day:%a %d %b}, {time}",
        },
    )


def load_slot_provider(config_dir: Path) -> SlotProvider:
    return SlotProvider(load_yaml_model(config_dir / SLOTS_FILE, SlotConfig))
