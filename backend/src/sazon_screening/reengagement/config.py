"""`config/reengagement.yaml`: the follow-up schedule, validated at startup (spec 008 FR-1).

The client owns these numbers (decisions.md: "configurable, no hard-coded defaults"), so
the loader is strict: a typo in a duration, steps out of order or an unknown timezone
stop the agent at startup with `reengagement.yaml: <path>: <problem>`.
"""

import re
from datetime import time, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from sazon_screening.config import ConfigError, load_yaml_model
from sazon_screening.config.models import ServiceAreasConfig
from sazon_screening.vocab import Country

REENGAGEMENT_FILE = "reengagement.yaml"
_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(s|m|h|d)\s*$")
_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def _duration(value: object) -> object:
    """ "2h", "30m", "3d", "45s" -> timedelta; anything else is left for Pydantic to reject."""
    if isinstance(value, str):
        match = _DURATION.match(value)
        if match is None:
            raise ValueError(f"'{value}' is not a duration like 30m, 2h or 3d")
        amount, unit = match.groups()
        return timedelta(**{_UNITS[unit]: float(amount)})
    return value


Duration = Annotated[timedelta, BeforeValidator(_duration)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FollowUpStep(_Strict):
    after: Duration  # since the candidate's last message (not since the previous step)
    kind: Literal["nudge", "last_call"]


class QuietHours(_Strict):
    start: time
    end: time

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if self.start == self.end:
            raise ValueError("start and end are the same time")
        return self

    def contains(self, moment: time) -> bool:
        """`start` inclusive, `end` exclusive; may wrap midnight (22:00-09:00)."""
        if self.start < self.end:
            return self.start <= moment < self.end
        return moment >= self.start or moment < self.end


class ReengagementConfig(_Strict):
    version: str
    enabled: bool = True
    tick_seconds: float = Field(30, gt=0)
    follow_ups: list[FollowUpStep] = Field(min_length=1)
    abandon_after: Duration
    quiet_hours: QuietHours | None = None
    whatsapp_window_hours: float = Field(24, gt=0)
    default_timezones: dict[Country, str]

    @field_validator("default_timezones")
    @classmethod
    def _timezones_exist(cls, value: dict[Country, str]) -> dict[Country, str]:
        for country, name in value.items():
            try:
                ZoneInfo(name)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError(f"{country.value}: unknown timezone '{name}'") from None
        return value

    @model_validator(mode="after")
    def _schedule_makes_sense(self) -> Self:
        afters = [step.after for step in self.follow_ups]
        if any(d <= timedelta(0) for d in [*afters, self.abandon_after]):
            raise ValueError("durations must be positive")
        if any(later <= earlier for earlier, later in pairwise(afters)):
            raise ValueError("follow_ups: `after` must be strictly increasing")
        kinds = [step.kind for step in self.follow_ups]
        if kinds[-1] != "last_call" or "last_call" in kinds[:-1]:
            raise ValueError("follow_ups: the last step, and only the last, is `last_call`")
        return self

    @property
    def window(self) -> timedelta:
        return timedelta(hours=self.whatsapp_window_hours)

    def scaled(self, time_scale: float) -> "ReengagementConfig":
        """Demo time (`REENGAGEMENT_TIME_SCALE`, e.g. 60: an hour passes in a minute).

        Every duration and the WhatsApp window shrink by the factor. Quiet hours are
        wall-clock times, so a scaled demo ignores them (a 2-minute nudge must not wait
        for 09:00). Scale 1 is the real schedule.
        """
        if time_scale == 1:
            return self
        return self.model_copy(
            update={
                "follow_ups": [
                    step.model_copy(update={"after": step.after / time_scale})
                    for step in self.follow_ups
                ],
                "abandon_after": self.abandon_after / time_scale,
                "whatsapp_window_hours": self.whatsapp_window_hours / time_scale,
                "quiet_hours": None,
            }
        )


def load_reengagement(config_dir: Path, service_areas: ServiceAreasConfig) -> ReengagementConfig:
    """Read `config/reengagement.yaml`; every served country needs a default timezone."""
    config = load_yaml_model(config_dir / REENGAGEMENT_FILE, ReengagementConfig)
    missing = [c.id.value for c in service_areas.countries if c.id not in config.default_timezones]
    if missing:
        raise ConfigError(
            f"{REENGAGEMENT_FILE}: default_timezones: missing {', '.join(missing)} "
            "(every country in service_areas.yaml needs one)"
        )
    return config


def timezone_for(
    config: ReengagementConfig,
    service_areas: ServiceAreasConfig,
    *,
    city_id: str | None,
    country: Country | None,
    default_country: Country,
) -> ZoneInfo:
    """The candidate's local time: the city's timezone, else the country's default."""
    for country_area in service_areas.countries:
        for city in country_area.cities:
            if city.id == city_id:
                return ZoneInfo(city.timezone)
    zones = config.default_timezones
    return ZoneInfo(zones.get(country or default_country) or zones[default_country])
