"""Pydantic models for the client-editable YAML config (FR-29, plan §3.10).

Validation happens once, at load time, so a typo in the YAML fails fast with a message
that names the problem (AC-35) instead of surfacing mid-conversation.
"""

import re
import unicodedata
from itertools import pairwise
from typing import Annotated, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from sazon_screening.engine.enums import Availability, Country, Language, VehicleType

# Lowercase slug: stable, URL-safe IDs that the record and the dashboard can rely on.
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]+$")]


def normalise(text: str) -> str:
    """Accent-, case- and punctuation-insensitive form used to compare place names.

    Temporary home: moves to `engine/location.py` with the location index (T11).
    """
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    spaced = re.sub(r"[^\w\s]|_", " ", without_marks.casefold())
    return " ".join(spaced.split())


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Area(_Strict):
    """Anything a candidate can name: display names per language plus aliases."""

    names: dict[Language, str]
    aliases: list[str] = []

    @field_validator("names")
    @classmethod
    def _names_cover_every_language(cls, names: dict[Language, str]) -> dict[Language, str]:
        missing = [lang.value for lang in Language if not names.get(lang)]
        if missing:
            raise ValueError(f"missing display name for language(s): {', '.join(missing)}")
        return names

    def match_keys(self) -> set[str]:
        """Normalised names and aliases, i.e. what a candidate's text is compared to."""
        return {normalise(text) for text in [*self.names.values(), *self.aliases]}


class Zone(Area):
    id: Slug


class City(Area):
    """A served city. No zones means the whole city is served."""

    id: Slug
    timezone: str
    zones: list[Zone] = []

    @field_validator("timezone")
    @classmethod
    def _timezone_exists(cls, timezone: str) -> str:
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"unknown timezone '{timezone}'") from None
        return timezone

    @model_validator(mode="after")
    def _zone_names_unique_in_city(self) -> Self:
        # Two zones of one city answering to the same name could never be told apart.
        # The same name in different cities is fine: country_hint or a question resolves it.
        owner: dict[str, str] = {}
        for zone in self.zones:
            for key in zone.match_keys():
                if key in owner and owner[key] != zone.id:
                    raise ValueError(
                        f"city '{self.id}': name '{key}' is used by more than one zone "
                        f"('{owner[key]}', '{zone.id}')"
                    )
                owner[key] = zone.id
        return self


class CountryArea(Area):
    id: Country
    cities: list[City]


class ServiceAreasConfig(_Strict):
    version: str
    countries: list[CountryArea] = Field(min_length=1)

    @model_validator(mode="after")
    def _ids_unique_across_file(self) -> Self:
        # IDs end up in records and dashboards, so one ID must mean one place.
        seen: set[str] = set()
        for country in self.countries:
            ids = [country.id.value]
            for city in country.cities:
                ids += [city.id, *(zone.id for zone in city.zones)]
            for area_id in ids:
                if area_id in seen:
                    raise ValueError(f"duplicate id '{area_id}' in service areas")
                seen.add(area_id)
        return self


# --- screening.yaml -------------------------------------------------------------------

PlatformId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]+$")]


class Platform(_Strict):
    """A delivery platform the candidate may have worked for (FR-21)."""

    id: PlatformId
    aliases: list[str] = []


class Thresholds(_Strict):
    """Loop guards and tolerances. Defaults are the decisions in spec §7 #11."""

    max_reasks: int = Field(2, ge=0)
    max_recap_rounds: int = Field(3, ge=1)
    max_consecutive_extraction_failures: int = Field(3, ge=1)
    abuse_close_count: int = Field(2, ge=1)
    fuzzy_match_min_score: int = Field(85, ge=50, le=100)
    # Below min_plausible_age we re-ask instead of disqualifying: "tengo 5" is more
    # likely years of experience than a five-year-old applying (plan OQ-6).
    min_plausible_age: int = Field(14, ge=0)
    max_plausible_age: int = Field(99, ge=1)
    experience_confirm_above_years: int = Field(40, ge=0)

    @model_validator(mode="after")
    def _age_bounds_ordered(self) -> Self:
        if self.min_plausible_age >= self.max_plausible_age:
            raise ValueError("min_plausible_age must be lower than max_plausible_age")
        return self


class ExperienceYearsScoring(_Strict):
    points_per_year: int = Field(ge=0)
    max_points: int = Field(ge=0)


class PlatformsScoring(_Strict):
    points_per_known_platform: int = Field(ge=0)
    max_points: int = Field(ge=0)


class AvailabilityScoring(_Strict):
    """One weight per `Availability` value (flat in YAML so ops can read it at a glance)."""

    full_time: int = Field(ge=0)
    part_time: int = Field(ge=0)
    weekends: int = Field(ge=0)
    max_points: int = Field(ge=0)

    def points_for(self, availability: Availability) -> int:
        points: int = getattr(self, availability.value)
        return points


class ScheduleScoring(_Strict):
    flexible: int = Field(ge=0)
    per_slot: int = Field(ge=0)
    max_points: int = Field(ge=0)


class StartDateBand(_Strict):
    """Start within `within_days` of the reference date earns `points`."""

    within_days: int = Field(ge=0)
    points: int = Field(ge=0)


class Buckets(_Strict):
    """Score >= high -> high; >= medium -> medium; else low."""

    high: int
    medium: int


class ScoringConfig(_Strict):
    experience_years: ExperienceYearsScoring
    platforms: PlatformsScoring
    availability: AvailabilityScoring
    schedule: ScheduleScoring
    start_date: list[StartDateBand] = Field(min_length=1)
    buckets: Buckets

    @property
    def max_score(self) -> int:
        return (
            self.experience_years.max_points
            + self.platforms.max_points
            + self.availability.max_points
            + self.schedule.max_points
            + max(band.points for band in self.start_date)
        )

    @model_validator(mode="after")
    def _bands_increase(self) -> Self:
        days = [band.within_days for band in self.start_date]
        if any(later <= earlier for earlier, later in pairwise(days)):
            raise ValueError(f"start_date bands must have strictly increasing within_days: {days}")
        return self

    @model_validator(mode="after")
    def _buckets_ordered(self) -> Self:
        high, medium = self.buckets.high, self.buckets.medium
        if not 0 < medium < high <= self.max_score:
            raise ValueError(
                f"bucket thresholds must satisfy 0 < medium < high <= max score "
                f"({self.max_score}); got medium={medium}, high={high}"
            )
        return self


class ScreeningConfig(_Strict):
    version: str
    default_country: Country
    min_age: dict[Country, int]
    # Typed as dict[str, bool] so the validator below can name an unknown vehicle type
    # in plain words instead of Pydantic's generic enum error (AC-35).
    license_required: dict[str, bool]
    platforms: list[Platform]
    thresholds: Thresholds = Thresholds()
    scoring: ScoringConfig

    @field_validator("license_required")
    @classmethod
    def _covers_every_vehicle(cls, required: dict[str, bool]) -> dict[str, bool]:
        allowed = [vehicle.value for vehicle in VehicleType]
        for key in required:
            if key not in allowed:
                raise ValueError(
                    f"unknown vehicle type '{key}' in license_required; "
                    f"allowed: {', '.join(allowed)}"
                )
        missing = [vehicle for vehicle in allowed if vehicle not in required]
        if missing:
            raise ValueError(f"license_required is missing vehicle type(s): {', '.join(missing)}")
        return required

    @field_validator("platforms")
    @classmethod
    def _platform_ids_unique(cls, platforms: list[Platform]) -> list[Platform]:
        seen: set[str] = set()
        for platform in platforms:
            if platform.id in seen:
                raise ValueError(f"duplicate platform id '{platform.id}'")
            seen.add(platform.id)
        return platforms

    def requires_license(self, vehicle: VehicleType) -> bool:
        return self.license_required[vehicle.value]


# --- both files -----------------------------------------------------------------------


class EngineConfig(_Strict):
    """Everything the engine needs, validated once and passed into every `step()` call."""

    service_areas: ServiceAreasConfig
    screening: ScreeningConfig

    @property
    def version(self) -> str:
        """Stamped on every record so an outcome can be traced to the rules that made it."""
        return f"{self.screening.version}+{self.service_areas.version}"

    @property
    def thresholds(self) -> Thresholds:
        return self.screening.thresholds

    @model_validator(mode="after")
    def _countries_consistent(self) -> Self:
        countries = [country.id for country in self.service_areas.countries]
        for country in countries:
            if country not in self.screening.min_age:
                raise ValueError(f"min_age has no value for country '{country}'")
        if self.screening.default_country not in countries:
            raise ValueError(
                f"default_country '{self.screening.default_country}' is not a configured country"
            )
        return self
