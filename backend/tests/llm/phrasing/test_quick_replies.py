"""T18: quick replies come from the action, never from the model (FR-14, AC-13)."""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine import (
    AskField,
    ConfirmAmbiguous,
    ConfirmValue,
    HandoffToHuman,
    OfferSlots,
    PrimaryAction,
    ReaskField,
    ShowRecap,
)
from sazon_screening.engine.state import Experience, Profile
from sazon_screening.llm.phrasing.catalog import MessageCatalog
from sazon_screening.llm.phrasing.quick_replies import QuickReply, quick_replies_for
from sazon_screening.vocab import FieldName, ReaskReason, Register
from tests.llm.builders import EL_CARMEN, action, ctx


def replies(
    primary: PrimaryAction,
    catalog: MessageCatalog,
    config: EngineConfig,
    register: Register = Register.es_ES,
) -> list[QuickReply]:
    return quick_replies_for(action(primary, register=register), ctx(), catalog, config)


@pytest.mark.ac("003:AC-13")
def test_vehicle_in_mexico(catalog: MessageCatalog, engine_config: EngineConfig) -> None:
    result = replies(AskField(field=FieldName.vehicle_type), catalog, engine_config, Register.es_MX)
    assert [r.id for r in result] == ["motorbike", "car", "bicycle", "e_bike", "none"]
    assert "Carro" in [r.label for r in result]


@pytest.mark.ac("003:AC-13")
@pytest.mark.parametrize(
    "field", [FieldName.full_name, FieldName.age, FieldName.location, FieldName.start_date]
)
def test_free_text_asks_have_none(
    catalog: MessageCatalog, engine_config: EngineConfig, field: FieldName
) -> None:
    assert replies(AskField(field=field), catalog, engine_config) == []


@pytest.mark.ac("003:AC-13")
def test_ambiguous_place_offers_the_area_ids(
    catalog: MessageCatalog, engine_config: EngineConfig
) -> None:
    result = replies(
        ConfirmAmbiguous(field=FieldName.location, options=EL_CARMEN), catalog, engine_config
    )
    assert [r.id for r in result] == ["mty-el-carmen", "val-el-carmen"]
    assert result[1].label == "El Carmen (Valencia)"


@pytest.mark.ac("003:AC-13")
def test_slots_offer_the_slot_ids(catalog: MessageCatalog, engine_config: EngineConfig) -> None:
    result = replies(OfferSlots(slot_ids=["s1", "s2"]), catalog, engine_config, Register.en)
    assert [(r.id, r.label) for r in result] == [
        ("s1", "Tue 14 Oct, 10am"),
        ("s2", "Wed 15 Oct, 4pm"),
    ]


@pytest.mark.parametrize(
    "primary",
    [
        AskField(field=FieldName.consent),
        AskField(field=FieldName.has_license),
        ShowRecap(profile=Profile()),
        ConfirmValue(field=FieldName.experience, value=Experience(years=45, platforms=[])),
        ReaskField(field=FieldName.consent, reason=ReaskReason.consent_required),
    ],
    ids=lambda p: p.type,
)
def test_yes_no_questions(
    catalog: MessageCatalog, engine_config: EngineConfig, primary: PrimaryAction
) -> None:
    assert replies(primary, catalog, engine_config) == [
        QuickReply(id="yes", label="Sí"),
        QuickReply(id="no", label="No"),
    ]


@pytest.mark.ac("003:AC-13")
def test_reask_with_options_offers_exactly_those(
    catalog: MessageCatalog, engine_config: EngineConfig
) -> None:
    primary = ReaskField(
        field=FieldName.location, reason=ReaskReason.not_recognised, options=["madrid", "cdmx"]
    )
    assert replies(primary, catalog, engine_config) == [
        QuickReply(id="madrid", label="Madrid"),
        QuickReply(id="cdmx", label="Ciudad de México"),
    ]


def test_actions_without_a_question_have_none(
    catalog: MessageCatalog, engine_config: EngineConfig
) -> None:
    assert replies(HandoffToHuman(), catalog, engine_config) == []
