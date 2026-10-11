"""What the engine is waiting for, as the extractor sees it (FR-5, plan §3.6).

The extractor only reads the latest message. The pending ask tells it what that
message answers ("sí" to consent vs "sí" to the recap) and which option ids exist,
so the model copies an id instead of inventing one.
"""

from collections.abc import Callable, Mapping

from pydantic import BaseModel, ConfigDict

from sazon_screening.config import EngineConfig
from sazon_screening.engine import AgeAnswer, ConversationState
from sazon_screening.llm.phrasing.labels import area_label
from sazon_screening.llm.slots import SlotDisplay
from sazon_screening.vocab import (
    Availability,
    FieldName,
    Language,
    PendingKind,
    ScheduleSlot,
    VehicleType,
)

# (group, value, language) -> label, e.g. ("vehicle_type", "car", es) -> "Coche".
# Injected: the message catalog (T15-T17) provides it; tests pass a stub.
EnumLabel = Callable[[str, str, Language], str]

_YES_NO = ("yes", "no")
_ENUM_OPTIONS: dict[FieldName, tuple[str, tuple[str, ...]]] = {
    FieldName.consent: ("yes_no", _YES_NO),
    FieldName.has_license: ("yes_no", _YES_NO),
    FieldName.vehicle_type: ("vehicle_type", tuple(v.value for v in VehicleType)),
    FieldName.availability: ("availability", tuple(v.value for v in Availability)),
    FieldName.schedule: ("schedule", tuple(v.value for v in ScheduleSlot)),
}


class OptionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str


class PendingView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: PendingKind
    field: FieldName | None
    options: list[OptionView]
    # recap / correction: what is stored now, so "no, es Chamberí" can be mapped
    current_values: dict[FieldName, str]

    def option_ids(self) -> set[str]:
        return {option.id for option in self.options}


def pending_view(
    state: ConversationState,
    config: EngineConfig,
    label: EnumLabel,
    slots: Mapping[str, SlotDisplay],
) -> PendingView:
    pending = state.pending
    reviewing = pending.kind in (PendingKind.recap, PendingKind.correction_field)
    return PendingView(
        kind=pending.kind,
        field=pending.field,
        options=_options(state, config, label, slots),
        current_values=_current_values(state, config, label) if reviewing else {},
    )


def _options(
    state: ConversationState,
    config: EngineConfig,
    label: EnumLabel,
    slots: Mapping[str, SlotDisplay],
) -> list[OptionView]:
    pending, language = state.pending, state.language
    if pending.kind is PendingKind.confirm_ambiguous:
        return [
            OptionView(id=option.id, label=area_label(option.id, config, language))
            for option in pending.options
        ]
    if pending.kind is PendingKind.slot:
        return [_slot_option(slot_id, slots, language) for slot_id in state.offered_slot_ids]
    if pending.kind in (PendingKind.confirm_value, PendingKind.recap):
        return _enum_options("yes_no", _YES_NO, label, language)
    if pending.kind is PendingKind.ask and pending.field in _ENUM_OPTIONS:
        group, values = _ENUM_OPTIONS[pending.field]
        return _enum_options(group, values, label, language)
    return []  # free-text asks and "what should I change?"


def _enum_options(
    group: str, values: tuple[str, ...], label: EnumLabel, language: Language
) -> list[OptionView]:
    return [OptionView(id=value, label=label(group, value, language)) for value in values]


def _slot_option(slot_id: str, slots: Mapping[str, SlotDisplay], language: Language) -> OptionView:
    display = slots.get(slot_id)
    return OptionView(id=slot_id, label=display.label(language) if display else slot_id)


def _current_values(
    state: ConversationState, config: EngineConfig, label: EnumLabel
) -> dict[FieldName, str]:
    """Stored values as short text, in profile order. Missing or unclear fields are left out."""
    profile, language = state.profile, state.language
    values: dict[FieldName, str] = {}
    if (name := profile.full_name.value) is not None:
        values[FieldName.full_name] = name
    if (age := profile.age.value) is not None:
        values[FieldName.age] = _age_text(age, label, language)
    if (vehicle := profile.vehicle_type.value) is not None:
        values[FieldName.vehicle_type] = label("vehicle_type", vehicle.value, language)
    if (has_license := profile.has_license.value) is not None:
        values[FieldName.has_license] = label("yes_no", "yes" if has_license else "no", language)
    if (location := profile.location.value) is not None:
        area_id = location.zone or location.city
        text = area_label(area_id, config, language) if area_id else location.raw_text
        values[FieldName.location] = text
    if (availability := profile.availability.value) is not None:
        labels = (label("availability", a.value, language) for a in availability)
        values[FieldName.availability] = ", ".join(labels)
    if (schedule := profile.schedule.value) is not None:
        labels = (label("schedule", s.value, language) for s in schedule)
        values[FieldName.schedule] = ", ".join(labels)
    if (experience := profile.experience.value) is not None:
        platforms = f" ({', '.join(experience.platforms)})" if experience.platforms else ""
        values[FieldName.experience] = f"{experience.years}{platforms}"
    if (start := profile.start_date.value) is not None:
        values[FieldName.start_date] = start.isoformat()
    return values


def _age_text(age: AgeAnswer, label: EnumLabel, language: Language) -> str:
    if age.age is not None:
        return str(age.age)
    if age.birth_year is not None:
        return f"born {age.birth_year}"
    return label("yes_no", "yes" if age.is_adult else "no", language)
