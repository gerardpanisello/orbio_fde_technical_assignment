"""Field validators (plan §3.6): proposed value -> Accepted | Rejected | NeedsConfirmation.

Validators only judge whether a value is a usable answer. They never decide
qualification: under-age, missing license and out-of-area are hard rules in rules.py,
applied to stored values. A rejected value becomes a re-ask with a reason code.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import Literal

from sazon_screening.config.areas import AreaRef, normalise
from sazon_screening.config.models import Platform
from sazon_screening.engine.inputs import (
    AbsoluteDate,
    AgeAnswer,
    Asap,
    DayMonth,
    ExperienceAnswer,
    Month,
    NextWeekday,
    Offset,
    StartDateExpr,
    Unclear,
)
from sazon_screening.engine.state import Experience
from sazon_screening.vocab import (
    Availability,
    Flag,
    ReaskReason,
    ScheduleSlot,
    VehicleType,
    Weekday,
)

# --- outcomes (internal: frozen dataclasses, never cross the engine boundary) -----------


@dataclass(frozen=True)
class Accepted[T]:
    value: T
    flags: tuple[Flag, ...] = ()


@dataclass(frozen=True)
class Rejected:
    reason: ReaskReason
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class NeedsConfirmation:
    """Usable but surprising (confirm_value) or matching several places (confirm_ambiguous)."""

    kind: Literal["value", "ambiguous"]
    value: Experience | None = None
    options: tuple[AreaRef, ...] = ()


# --- consent & name ----------------------------------------------------------------------


def validate_consent(answer: bool | Unclear) -> Accepted[bool] | Rejected:
    """Only an explicit yes or no counts (FR-7): we never assume consent."""
    if isinstance(answer, Unclear):
        return Rejected(ReaskReason.consent_required)
    return Accepted(answer)


# Phone keyboards often type a typographic apostrophe instead of ' (see tests).
_NAME_PUNCTUATION = frozenset(" -'\N{RIGHT SINGLE QUOTATION MARK}")


def validate_name(answer: str | Unclear, *, surname_requested: bool) -> Accepted[str] | Rejected:
    """Letters (accents included), spaces, hyphens and apostrophes; ideally 2+ words (FR-16).

    A first name alone gets one request for the surname. After that we accept it with a
    flag: the name is required but not qualifying, so it must never block a candidate.
    """
    if isinstance(answer, Unclear):
        return Rejected(ReaskReason.unclear)
    name = " ".join(answer.split())
    if not any(ch.isalpha() for ch in name):
        return Rejected(ReaskReason.unclear)
    if not all(ch.isalpha() or ch in _NAME_PUNCTUATION for ch in name):
        return Rejected(ReaskReason.invalid_characters)
    if len(name.split()) < 2:
        if not surname_requested:
            return Rejected(ReaskReason.surname_missing)
        return Accepted(name, flags=(Flag.surname_missing,))
    return Accepted(name)


# --- knock-out answers (age, vehicle, license) -------------------------------------------


def age_range(answer: AgeAnswer, today: date | None) -> tuple[int, int] | None:
    """The youngest and oldest the candidate can be, or None if only `is_adult` is known.

    An explicit age is exact. A birth year gives two possible ages, because we do not
    know whether the birthday has passed this year (and needs `today` to say anything).
    """
    if answer.age is not None:
        return answer.age, answer.age
    if answer.birth_year is not None and today is not None:
        oldest = today.year - answer.birth_year
        return oldest - 1, oldest
    return None


def validate_age(
    answer: AgeAnswer | Unclear,
    *,
    min_plausible: int,
    max_plausible: int,
    min_age: int,
    today: date,
) -> Accepted[AgeAnswer] | Rejected:
    """Re-ask implausible or borderline ages instead of judging them (FR-17).

    "Tengo 5" is more likely years of experience than a child applying, and "150" is a
    typo. A birth year that could mean 17 or 18 is re-asked: ambiguity never disqualifies.
    Under-age itself is NOT decided here: rules.py applies the minimum age per country.
    """
    if isinstance(answer, Unclear):
        return Rejected(ReaskReason.unclear)
    ages = age_range(answer, today)
    if ages is None:
        return Accepted(answer)
    youngest, oldest = ages
    if oldest < min_plausible or youngest > max_plausible:
        return Rejected(ReaskReason.implausible_value)
    if youngest < min_age <= oldest:
        return Rejected(ReaskReason.unclear)
    return Accepted(answer)


_VEHICLE_OPTIONS = tuple(vehicle.value for vehicle in VehicleType)


def validate_vehicle(answer: VehicleType | Unclear) -> Accepted[VehicleType] | Rejected:
    if isinstance(answer, Unclear):
        return Rejected(ReaskReason.unclear, options=_VEHICLE_OPTIONS)
    return Accepted(answer)


def validate_license(answer: bool | Unclear) -> Accepted[bool] | Rejected:
    if isinstance(answer, Unclear):
        return Rejected(ReaskReason.unclear)
    return Accepted(answer)


# --- profile answers (soft fields: they rank, never reject) --------------------------------


def validate_availability(
    answer: list[Availability] | Unclear,
) -> Accepted[list[Availability]] | Rejected:
    return _validate_selection(answer, Availability)


def validate_schedule(
    answer: list[ScheduleSlot] | Unclear,
) -> Accepted[list[ScheduleSlot]] | Rejected:
    return _validate_selection(answer, ScheduleSlot)


def _validate_selection[E: StrEnum](
    answer: list[E] | Unclear, options: type[E]
) -> Accepted[list[E]] | Rejected:
    """Non-empty multi-choice (FR-20). Stored de-duplicated in enum order (deterministic JSON)."""
    all_options = tuple(option.value for option in options)
    if isinstance(answer, Unclear):
        return Rejected(ReaskReason.unclear, options=all_options)
    if not answer:
        return Rejected(ReaskReason.empty_selection, options=all_options)
    return Accepted([option for option in options if option in answer])


def validate_experience(
    answer: ExperienceAnswer | Unclear, *, platforms: Sequence[Platform], confirm_above: int
) -> Accepted[Experience] | Rejected | NeedsConfirmation:
    """Years plus platforms (FR-21). Surprising years are confirmed, never rejected."""
    if isinstance(answer, Unclear):
        return Rejected(ReaskReason.unclear)
    if answer.years == "none":
        return Accepted(Experience(years=0, platforms=[]))
    if answer.years is None:
        return Rejected(ReaskReason.missing_years)
    if answer.years < 0:
        return Rejected(ReaskReason.negative_value)
    platform_ids = normalise_platforms(answer.platforms, platforms)
    experience = Experience(years=answer.years, platforms=platform_ids)
    if answer.years > confirm_above:
        return NeedsConfirmation("value", value=experience)
    return Accepted(experience)


def normalise_platforms(raw: Sequence[str], platforms: Sequence[Platform]) -> list[str]:
    """Map names to config platform ids; keep unknown ones as `other:<text>` for the recruiter.

    Exact match only (after normalising case, accents and punctuation): a fuzzy guess
    here would award score points for a platform the candidate never named.
    """
    by_key = {
        normalise(name): platform.id
        for platform in platforms
        for name in (platform.id, *platform.aliases)
    }
    ids = set()
    for text in raw:
        cleaned = " ".join(text.split())
        if cleaned:
            ids.add(by_key.get(normalise(cleaned), f"other:{cleaned}"))
    return sorted(ids)


# --- start date (FR-22) ------------------------------------------------------------------


def resolve_start_date(expr: StartDateExpr, today: date) -> tuple[date, bool]:
    """Calendar arithmetic on the extractor's structure. Returns (date, was_normalised).

    `next_weekday` is the next occurrence strictly after today: on a Monday, "el lunes"
    means next week's Monday. A date in the past is moved to today and flagged.
    Month-level answers (`offset` in months, `month`) resolve to the 1st of that month,
    or today when that month is the current one: that is the candidate's answer, not a
    past date, so it is not flagged as normalised.
    """
    match expr:
        case Asap():
            resolved = today
        case AbsoluteDate(on=on):
            resolved = on
        case Offset(amount=amount, unit="days"):
            resolved = today + timedelta(days=amount)
        case Offset(amount=amount, unit="weeks"):
            resolved = today + timedelta(weeks=amount)
        case Offset(amount=amount, unit="months"):
            return max(_add_months(today.replace(day=1), amount), today), False
        case NextWeekday(weekday=weekday):
            days_ahead = (list(Weekday).index(weekday) - today.weekday()) % 7 or 7
            resolved = today + timedelta(days=days_ahead)
        case DayMonth(day=day, month=month):
            resolved = next_day_month(day, month, today)
        case Month(month=month):
            return max(next_day_month(1, month, today.replace(day=1)), today), False
    if resolved < today:
        return today, True
    return resolved, False


def is_month_level(expr: StartDateExpr) -> bool:
    """ "el mes que viene", "en noviembre": the recruiter sees the month, not a day."""
    return isinstance(expr, Month) or (isinstance(expr, Offset) and expr.unit == "months")


def _add_months(first_of_month: date, months: int) -> date:
    """The 1st of the month `months` after `first_of_month` (ValueError past year 9999)."""
    index = first_of_month.month - 1 + months
    return date(first_of_month.year + index // 12, index % 12 + 1, 1)


def next_day_month(day: int, month: int, today: date) -> date:
    """The next date on or after today with this day and month.

    Looks up to 8 years ahead so 29/02 finds the next leap year. Raises ValueError for a
    date that never exists (31/02, month 13); the validator turns that into a re-ask.
    """
    for year in range(today.year, today.year + 9):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue  # 29/02 in a non-leap year, or an impossible date
        if candidate >= today:
            return candidate
    raise ValueError(f"no date {day}/{month}")


def validate_start_date(answer: StartDateExpr | Unclear, today: date) -> Accepted[date] | Rejected:
    if isinstance(answer, Unclear):
        return Rejected(ReaskReason.unclear)
    if isinstance(answer, Offset) and answer.amount < 0:
        return Rejected(ReaskReason.negative_value)
    try:
        resolved, normalised = resolve_start_date(answer, today)
    except (OverflowError, ValueError):  # "in a billion weeks", 31/02: ask again
        return Rejected(ReaskReason.implausible_value)
    flags: tuple[Flag, ...] = (Flag.start_date_normalised,) if normalised else ()
    if is_month_level(answer):
        flags += (Flag.start_date_approximate,)
    return Accepted(resolved, flags=flags)
