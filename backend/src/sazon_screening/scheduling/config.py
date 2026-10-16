"""`config/interview_slots.yaml`: interview availability per city, validated at startup.

The YAML is only the first-start seed (spec 010 FR-1): it fills the `interview_availability`
table for cities that have no row yet, and from then on recruiters edit the table from the
dashboard. `AvailabilitySettings` is therefore the one validation for both: a bad YAML
stops the agent at startup, a bad dashboard edit is a 422 (AC-7).
"""

from datetime import time
from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from sazon_screening.config import ConfigError, load_yaml_model
from sazon_screening.config.models import ServiceAreasConfig
from sazon_screening.vocab import Weekday

SLOTS_FILE = "interview_slots.yaml"
Time = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Place = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AvailabilitySettings(_Strict):
    """When one city interviews: on `weekdays`, at `times` (local), `capacity` candidates
    per slot (interviewers in parallel), offered `days_ahead` working days from tomorrow."""

    weekdays: list[Weekday] = Field(min_length=1)
    times: list[Time] = Field(min_length=1, max_length=24)
    capacity: int = Field(ge=1, le=50)
    duration_min: int = Field(ge=5, le=240)
    days_ahead: int = Field(ge=1, le=15)
    place: Place  # an address, or "Videollamada" + link (fictional in the demo)

    @model_validator(mode="after")
    def _sorted_and_unique(self) -> Self:
        """Stored in a canonical order, so the week view and the offer read the same."""
        if len(set(self.times)) != len(self.times):
            raise ValueError("times: each time only once")
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("weekdays: each day only once")
        order = list(Weekday)
        object.__setattr__(self, "times", sorted(self.times))
        object.__setattr__(self, "weekdays", sorted(self.weekdays, key=order.index))
        return self


class PartialAvailability(_Strict):
    """Defaults, a city's overrides, or a dashboard PATCH: any subset of the settings."""

    weekdays: list[Weekday] | None = None
    times: list[Time] | None = None
    capacity: int | None = None
    duration_min: int | None = None
    days_ahead: int | None = None
    place: Place | None = None

    def over(self, base: dict[str, object]) -> dict[str, object]:
        return {**base, **self.model_dump(exclude_none=True)}


class ReminderConfig(_Strict):
    """FR-6: the day-before reminder, at `at` local time (quiet hours still apply)."""

    enabled: bool = True
    at: time = time(18, 0)


class InterviewConfig(_Strict):
    version: str
    max_slots: int | None = Field(default=3, gt=0, le=20)  # None: every open slot
    reminder: ReminderConfig = ReminderConfig()
    defaults: PartialAvailability = PartialAvailability()
    cities: dict[str, PartialAvailability]

    @model_validator(mode="after")
    def _every_city_complete(self) -> Self:
        for city in self.cities:
            try:
                self.availability(city)
            except ValueError as error:
                raise ValueError(f"cities.{city}: {error}") from None
        return self

    def availability(self, city: str) -> AvailabilitySettings:
        """The city's settings: its overrides on top of the defaults."""
        merged = self.cities[city].over(self.defaults.over({}))
        return AvailabilitySettings.model_validate(merged)


def load_interview_config(config_dir: Path, service_areas: ServiceAreasConfig) -> InterviewConfig:
    """Read the YAML; every city must be a served city (a typo would never be offered)."""
    config = load_yaml_model(config_dir / SLOTS_FILE, InterviewConfig)
    served = {city.id for country in service_areas.countries for city in country.cities}
    unknown = sorted(set(config.cities) - served)
    if unknown:
        raise ConfigError(
            f"{SLOTS_FILE}: cities: {', '.join(unknown)}: not a city in service_areas.yaml"
        )
    return config
