"""Human labels for ids and stored values (plan §3.7).

The engine speaks in ids (enum values, area ids, slot ids). These functions turn them
into words for one register, from the message catalog (enums), `service_areas.yaml`
(place names) and the caller's slot display data. Used by templates, quick replies,
the extractor's pending view and the phrasing request.
"""

from collections.abc import Mapping
from datetime import date, timedelta

from sazon_screening.config import EngineConfig
from sazon_screening.engine import AgeAnswer, Profile
from sazon_screening.llm.phrasing.catalog import Labels
from sazon_screening.llm.slots import SlotDisplay
from sazon_screening.vocab import FieldName, FieldStatus, Language, Weekday

# Fields whose values are enum ids, and the catalog label group for them.
ENUM_GROUPS: dict[FieldName, str] = {
    FieldName.consent: "yes_no",
    FieldName.has_license: "yes_no",
    FieldName.vehicle_type: "vehicle_type",
    FieldName.availability: "availability",
    FieldName.schedule: "schedule",
}


def area_label(area_id: str, config: EngineConfig, language: Language) -> str:
    """A zone reads "Coyoacán (Ciudad de México)", a city "Madrid", an unknown id itself.

    The city is part of a zone's label because zone names repeat across cities
    ("Centro", "El Carmen"): it is exactly what the candidate must choose between.
    """
    for country in config.service_areas.countries:
        for city in country.cities:
            city_name = city.names[language]
            if city.id == area_id:
                return city_name
            for zone in city.zones:
                if zone.id == area_id:
                    return f"{zone.names[language]} ({city_name})"
    return area_id


def slot_label(slot_id: str, slots: Mapping[str, SlotDisplay], language: Language) -> str:
    display = slots.get(slot_id)
    return display.label(language) if display else slot_id


def option_label(
    field: FieldName,
    option_id: str,
    *,
    config: EngineConfig,
    language: Language,
    labels: Labels,
    slots: Mapping[str, SlotDisplay],
) -> str:
    """The label of one re-ask option, whatever kind of id it is."""
    if field in ENUM_GROUPS:
        return labels.group(ENUM_GROUPS[field]).get(option_id, option_id)
    if field is FieldName.slot:
        return slot_label(option_id, slots, language)
    return area_label(option_id, config, language)  # location / zone options are areas


def field_values(
    profile: Profile,
    config: EngineConfig,
    language: Language,
    labels: Labels,
    *,
    today: date | None = None,
) -> dict[FieldName, str]:
    """Stored values as short text, in profile order. Missing or unclear fields are left out.

    Used for the recap (the candidate checks it) and for the extractor's view of what is
    stored (so "no, es Chamberí" can be mapped).
    """
    values: dict[FieldName, str] = {}
    if (name := profile.full_name.value) is not None:
        values[FieldName.full_name] = display_name(name)
    if (age := profile.age.value) is not None:
        values[FieldName.age] = _age_text(age, labels)
    if (vehicle := profile.vehicle_type.value) is not None:
        values[FieldName.vehicle_type] = labels.vehicle_type[vehicle]
    license_slot = profile.has_license
    if license_slot.value is not None and license_slot.status is FieldStatus.valid:
        values[FieldName.has_license] = labels.yes_no[_yes_no(license_slot.value)]
    if (location := profile.location.value) is not None:
        area_id = location.zone or location.city
        text = area_label(area_id, config, language) if area_id else location.raw_text
        values[FieldName.location] = text
    if (availability := profile.availability.value) is not None:
        values[FieldName.availability] = ", ".join(labels.availability[a] for a in availability)
    if (schedule := profile.schedule.value) is not None:
        values[FieldName.schedule] = ", ".join(labels.schedule[s] for s in schedule)
    if (experience := profile.experience.value) is not None:
        values[FieldName.experience] = _experience_text(
            experience.years, experience.platforms, labels
        )
    if (start := profile.start_date.value) is not None:
        values[FieldName.start_date] = _start_text(start, today, labels)
    return values


def display_name(name: str) -> str:
    """ "lucía fernández ruiz" reads "Lucía Fernández Ruiz". Display only (recap, summary,
    first name): the profile keeps what the candidate wrote. A word they wrote with any
    capital ("McDonald", "JOSÉ") stays as written, and particles ("de la") stay lowercase.
    """
    words = name.split()
    shown = [
        word if index and word in _NAME_PARTICLES else _capitalise(word)
        for index, word in enumerate(words)
    ]
    return " ".join(shown)


_NAME_PARTICLES = frozenset({"de", "del", "la", "las", "los", "y", "e", "da", "das", "do", "dos"})


def _capitalise(word: str) -> str:
    if word != word.lower():
        return word
    return "-".join(part[:1].upper() + part[1:] for part in word.split("-"))


def _experience_text(years_done: int, platform_ids: list[str], labels: Labels) -> str:
    """0 years and no platform is "no experience"; 0 years with one is under a year
    ("6 meses en Glovo" is stored as 0 years: the engine counts whole years).
    """
    platforms = ", ".join(_platform_name(p) for p in platform_ids)
    if years_done == 0 and not platforms:
        return labels.no_experience
    if years_done == 0:
        years = labels.less_than_a_year
    else:
        unit = labels.year if years_done == 1 else labels.years
        years = f"{years_done} {unit}"
    return f"{years} ({platforms})" if platforms else years


def _start_text(start: date, today: date | None, labels: Labels) -> str:
    """ "mañana, miércoles 14/10/2026": candidates who said "mañana" must recognise it
    (eval 2026-10-12: a bare "14/10/2026" was corrected again and again).
    """
    text = f"{labels.weekdays[list(Weekday)[start.weekday()]]} {start:%d/%m/%Y}"
    if today is not None and start == today:
        return f"{labels.today}, {text}"
    if today is not None and start == today + timedelta(days=1):
        return f"{labels.tomorrow}, {text}"
    return text


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _age_text(age: AgeAnswer, labels: Labels) -> str:
    if age.age is not None:
        return str(age.age)
    if age.birth_year is not None:
        return f"{age.birth_year} ({labels.birth_year})"
    return labels.adult[_yes_no(age.is_adult is True)]


def _platform_name(platform_id: str) -> str:
    """Config ids read as names ("uber_eats" -> "Uber Eats"); free text stays as written."""
    if platform_id.startswith("other:"):
        return platform_id.removeprefix("other:")
    return platform_id.replace("_", " ").title()
