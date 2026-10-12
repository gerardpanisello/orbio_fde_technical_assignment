"""T10: what the engine is waiting for, as the extractor sees it (FR-5)."""

from collections.abc import Callable

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine import ConversationState, start
from sazon_screening.llm.extraction.pending import OptionView, PendingView, pending_view
from sazon_screening.llm.phrasing.catalog import MessageCatalog
from sazon_screening.llm.slots import SlotDisplay
from sazon_screening.vocab import FieldName, Language, PendingKind, Stage
from tests.engine.builders import Convo, adult, consent, license, loc, name, no, vehicle

SLOTS = {
    "s1": SlotDisplay(id="s1", labels={Language.es: "martes 10:00", Language.en: "Tuesday 10am"}),
    "s2": SlotDisplay(id="s2", labels={Language.es: "miércoles 16:00", Language.en: "Wed 4pm"}),
}


View = Callable[[ConversationState, EngineConfig], PendingView]


@pytest.fixture
def view(catalog: MessageCatalog) -> Callable[[ConversationState, EngineConfig], PendingView]:
    def build(state: ConversationState, config: EngineConfig) -> PendingView:
        return pending_view(state, config, catalog, SLOTS)

    return build


def test_fresh_state_asks_for_consent_with_yes_no(
    engine_config: EngineConfig, view: View, catalog: MessageCatalog
) -> None:
    state, _ = start(engine_config)
    pending = view(state, engine_config)
    assert (pending.kind, pending.field) == (PendingKind.ask, FieldName.consent)
    assert pending.options == [
        OptionView(id="yes", label="Sí"),
        OptionView(id="no", label="No"),
    ]
    assert pending.current_values == {}


def test_closed_field_lists_its_enum_values(
    engine_config: EngineConfig, view: View, catalog: MessageCatalog
) -> None:
    c = Convo(engine_config).say(consent(True), name("Ana López"), adult())
    pending = view(c.state, engine_config)
    assert pending.field is FieldName.vehicle_type
    assert [o.id for o in pending.options] == ["motorbike", "car", "bicycle", "e_bike", "none"]


def test_free_text_field_has_no_options(
    engine_config: EngineConfig, view: View, catalog: MessageCatalog
) -> None:
    c = Convo(engine_config).say(consent(True))
    assert view(c.state, engine_config).options == []


def test_ambiguous_place_offers_both_areas_with_city_names(
    engine_config: EngineConfig, view: View, catalog: MessageCatalog
) -> None:
    c = Convo(engine_config).say(
        consent(True), name("Ana López"), adult(), vehicle("car"), license(True)
    )
    c.say(loc("El Carmen"))
    pending = view(c.state, engine_config)
    assert pending.kind is PendingKind.confirm_ambiguous
    assert [(o.id, o.label) for o in pending.options] == [
        ("mty-el-carmen", "El Carmen (Monterrey)"),
        ("val-el-carmen", "El Carmen (Valencia)"),
    ]


def test_scheduling_offers_the_slots_in_the_candidate_language(
    engine_config: EngineConfig, view: View
) -> None:
    c = Convo(engine_config).advance_to(Stage.scheduling)
    pending = view(c.state, engine_config)
    assert pending.kind is PendingKind.slot
    assert [(o.id, o.label) for o in pending.options] == [
        ("s1", "martes 10:00"),
        ("s2", "miércoles 16:00"),
    ]


def test_unknown_slot_falls_back_to_its_id(
    engine_config: EngineConfig, view: View, catalog: MessageCatalog
) -> None:
    c = Convo(engine_config).advance_to(Stage.scheduling)
    pending = pending_view(c.state, engine_config, catalog, {})
    assert [o.label for o in pending.options] == ["s1", "s2"]


def test_recap_shows_the_current_values(
    engine_config: EngineConfig, view: View, catalog: MessageCatalog
) -> None:
    c = Convo(engine_config).advance_to(Stage.recap)
    pending = view(c.state, engine_config)
    assert pending.kind is PendingKind.recap
    assert [o.id for o in pending.options] == ["yes", "no"]
    values = pending.current_values
    assert values[FieldName.full_name] == "Ana López"
    assert values[FieldName.location] == "Coyoacán (Ciudad de México)"
    assert values[FieldName.vehicle_type] == "Moto"
    assert values[FieldName.availability] == "Jornada completa, Fines de semana"
    assert values[FieldName.experience] == "3 años (Glovo)"
    assert values[FieldName.start_date] == "lunes 12/10/2026"  # no today here: weekday only


def test_correction_field_also_shows_the_values(
    engine_config: EngineConfig, view: View, catalog: MessageCatalog
) -> None:
    c = Convo(engine_config).advance_to(Stage.recap).say(no())
    pending = view(c.state, engine_config)
    assert pending.kind is PendingKind.correction_field
    assert FieldName.location in pending.current_values
