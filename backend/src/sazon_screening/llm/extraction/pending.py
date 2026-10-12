"""What the engine is waiting for, as the extractor sees it (FR-5, plan §3.6).

The extractor only reads the latest message. The pending ask tells it what that
message answers ("sí" to consent vs "sí" to the recap) and which option ids exist,
so the model copies an id instead of inventing one.
"""

from collections.abc import Mapping
from datetime import date

from pydantic import BaseModel, ConfigDict

from sazon_screening.config import EngineConfig
from sazon_screening.engine import ConversationState
from sazon_screening.llm.phrasing.catalog import Labels, MessageCatalog
from sazon_screening.llm.phrasing.labels import ENUM_GROUPS, area_label, field_values, slot_label
from sazon_screening.llm.slots import SlotDisplay
from sazon_screening.vocab import FieldName, PendingKind


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
    catalog: MessageCatalog,
    slots: Mapping[str, SlotDisplay],
    *,
    today: date | None = None,
) -> PendingView:
    pending = state.pending
    labels = catalog.for_language(state.language).labels
    reviewing = pending.kind in (PendingKind.recap, PendingKind.correction_field)
    current = (
        field_values(state.profile, config, state.language, labels, today=today)
        if reviewing
        else {}
    )
    return PendingView(
        kind=pending.kind,
        field=pending.field,
        options=_options(state, config, labels, slots),
        current_values=current,
    )


def _options(
    state: ConversationState,
    config: EngineConfig,
    labels: Labels,
    slots: Mapping[str, SlotDisplay],
) -> list[OptionView]:
    pending, language = state.pending, state.language
    if pending.kind is PendingKind.confirm_ambiguous:
        return [
            OptionView(id=option.id, label=area_label(option.id, config, language))
            for option in pending.options
        ]
    if pending.kind is PendingKind.slot:
        return [
            OptionView(id=slot_id, label=slot_label(slot_id, slots, language))
            for slot_id in state.offered_slot_ids
        ]
    if pending.kind in (PendingKind.confirm_value, PendingKind.recap):
        return _enum_options(labels.yes_no)
    if pending.kind is PendingKind.ask and pending.field in ENUM_GROUPS:
        return _enum_options(labels.group(ENUM_GROUPS[pending.field]))
    return []  # free-text asks and "what should I change?"


def _enum_options(group: Mapping[str, str]) -> list[OptionView]:
    return [OptionView(id=value, label=label) for value, label in group.items()]
