"""T16/T17: the shipped template text and its rendering (FR-2, FR-12, FR-13, FR-16)."""

import re

import pytest

from sazon_screening.config import EngineConfig, load_config
from sazon_screening.engine import (
    AckCorrection,
    AnswerFaq,
    AskField,
    CloseDisqualified,
    PrimaryAction,
    ReaskField,
    Redirect,
)
from sazon_screening.engine.state import Experience, Profile, Slot
from sazon_screening.llm.phrasing.catalog import MessageCatalog
from sazon_screening.llm.phrasing.labels import field_values
from sazon_screening.llm.phrasing.language import dominant_language
from sazon_screening.llm.phrasing.policy import expects_question, length_cap
from sazon_screening.llm.phrasing.templates import render_template
from sazon_screening.llm.settings import LengthCaps
from sazon_screening.vocab import (
    DisqualificationReason,
    FieldName,
    FieldStatus,
    ReaskReason,
    Register,
)
from tests.engine.conftest import TODAY
from tests.llm.builders import PRIVACY_URL, action, ctx, language_of, sample_primaries
from tests.paths import FIXTURE_CONFIG_DIR

CAPS = LengthCaps()
EMOJI = re.compile("[\U0001f300-\U0001faff\u2600-\u27bf]")
PRIMARIES = sample_primaries(load_config(FIXTURE_CONFIG_DIR))


@pytest.mark.ac("003:AC-14")
def test_license_vocabulary_follows_the_register(catalog: MessageCatalog) -> None:
    spain = catalog.for_register(Register.es_ES).templates.ask_field[FieldName.has_license]
    mexico = catalog.for_register(Register.es_MX).templates.ask_field[FieldName.has_license]
    assert "carné" in spain
    assert "licencia de manejo" in mexico


@pytest.mark.parametrize("register", list(Register))
def test_greeting_names_sofi_and_links_the_privacy_notice(
    catalog: MessageCatalog, register: Register
) -> None:
    greeting = catalog.for_register(register).templates.greeting
    assert "Sofi" in greeting
    assert "{privacy_url}" in greeting


@pytest.mark.parametrize("register", list(Register))
def test_no_license_close_leaves_the_door_open(catalog: MessageCatalog, register: Register) -> None:
    text = catalog.for_register(register).templates.close_disqualified[
        DisqualificationReason.no_license
    ]
    assert any(word in text for word in ("escríbenos", "write to us"))


@pytest.mark.ac("003:AC-11")
@pytest.mark.parametrize("register", list(Register))
@pytest.mark.parametrize("primary", PRIMARIES, ids=lambda p: p.type)
def test_every_action_renders_within_the_rules(
    catalog: MessageCatalog, engine_config: EngineConfig, register: Register, primary: PrimaryAction
) -> None:
    act = action(primary, register=register)
    text = render_template(act, ctx(), catalog, engine_config)
    assert text.strip()
    assert len(text) <= length_cap(act, CAPS, faq_answer=None)
    assert text.count("?") == (1 if expects_question(act) else 0), text
    assert dominant_language(text) in (None, language_of(register)), text
    assert "{" not in text  # every placeholder filled


@pytest.mark.ac("003:AC-14")
@pytest.mark.parametrize("register", list(Register))
@pytest.mark.parametrize("reason", list(DisqualificationReason))
def test_disqualification_has_no_emoji(
    catalog: MessageCatalog,
    engine_config: EngineConfig,
    register: Register,
    reason: DisqualificationReason,
) -> None:
    act = action(CloseDisqualified(reason=reason), register=register)
    assert not EMOJI.search(render_template(act, ctx(), catalog, engine_config))


@pytest.mark.ac("003:AC-15")
def test_redirect_comes_first_with_one_question(
    catalog: MessageCatalog, engine_config: EngineConfig
) -> None:
    act = action(AskField(field=FieldName.schedule), Redirect(reason="off_topic"))
    text = render_template(act, ctx(), catalog, engine_config)
    assert text.startswith("Solo puedo ayudarte con tu solicitud")
    assert text.count("?") == 1


@pytest.mark.ac("003:AC-15")
def test_faq_without_an_answer_uses_the_holding_phrase(
    catalog: MessageCatalog, engine_config: EngineConfig
) -> None:
    act = action(AskField(field=FieldName.age), AnswerFaq())
    assert "lo consulto con el equipo" in render_template(act, ctx(), catalog, engine_config)
    answered = render_template(act, ctx(faq_answer="Pagamos por pedido."), catalog, engine_config)
    assert answered.startswith("Pagamos por pedido.")
    assert "lo consulto" not in answered


def test_correction_is_acknowledged_with_field_names(
    catalog: MessageCatalog, engine_config: EngineConfig
) -> None:
    act = action(AskField(field=FieldName.age), AckCorrection(fields=[FieldName.location]))
    text = render_template(act, ctx(), catalog, engine_config)
    assert text.startswith("Hecho, he actualizado: ciudad y barrio.")


@pytest.mark.ac("003:AC-16")
@pytest.mark.parametrize("register", list(Register))
def test_greeting(catalog: MessageCatalog, engine_config: EngineConfig, register: Register) -> None:
    act = action(AskField(field=FieldName.consent), register=register)
    text = render_template(act, ctx(is_greeting=True), catalog, engine_config)
    assert "Sofi" in text
    assert any(word in text for word in ("automático", "automática", "automated"))
    assert PRIVACY_URL in text
    assert text.count("?") == 1
    assert len(text) <= CAPS.default


def test_reask_lists_option_labels(catalog: MessageCatalog, engine_config: EngineConfig) -> None:
    primary = ReaskField(field=FieldName.vehicle_type, reason=ReaskReason.unclear, options=["car"])
    act = action(primary, register=Register.es_MX)
    assert render_template(act, ctx(), catalog, engine_config).endswith("? (Carro)")


def test_recap_lists_the_values(catalog: MessageCatalog, engine_config: EngineConfig) -> None:
    recap = next(p for p in PRIMARIES if p.type == "show_recap")
    text = render_template(action(recap), ctx(), catalog, engine_config)
    assert "• Nombre completo: Ana López" in text
    assert "• Ciudad y barrio: Coyoacán (Ciudad de México)" in text
    assert f"{TODAY:%d/%m/%Y}" in text


def test_slots_are_numbered(catalog: MessageCatalog, engine_config: EngineConfig) -> None:
    slots = next(p for p in PRIMARIES if p.type == "offer_slots")
    text = render_template(action(slots, register=Register.en), ctx(), catalog, engine_config)
    assert "1. Tue 14 Oct, 10am\n2. Wed 15 Oct, 4pm" in text


@pytest.mark.parametrize(
    ("register", "years", "expected"),
    [
        (Register.es_ES, 1, "1 año (Glovo)"),
        (Register.es_ES, 3, "3 años (Glovo)"),
        (Register.es_MX, 1, "1 año (Glovo)"),
        (Register.en, 1, "1 year (Glovo)"),
        (Register.en, 0, "0 years (Glovo)"),
    ],
)
def test_recap_years_of_experience_agree_in_number(
    catalog: MessageCatalog,
    engine_config: EngineConfig,
    register: Register,
    years: int,
    expected: str,
) -> None:
    """Found by the sample conversations: the recap said "1 años"."""
    profile = Profile()
    profile.experience = Slot(
        status=FieldStatus.valid, value=Experience(years=years, platforms=["glovo"])
    )
    labels = catalog.for_register(register).labels
    values = field_values(profile, engine_config, language_of(register), labels)
    assert values[FieldName.experience] == expected


@pytest.mark.parametrize("register", list(Register))
def test_experience_is_one_question_with_an_example(
    catalog: MessageCatalog, register: Register
) -> None:
    """Eval 2026-10-12: "how many years, and with which apps?" read as two questions."""
    templates = catalog.for_register(register).templates
    for text in (
        templates.ask_field[FieldName.experience],
        templates.reask_field[ReaskReason.missing_years],
    ):
        assert text.count("?") == 1
        assert re.search(r"«[^»]+»|\"[^\"]+\"", text), text  # the example, quoted
        assert " y con qué" not in text
        assert ", and with which" not in text


@pytest.mark.parametrize("register", list(Register))
def test_opt_out_close_confirms_the_data_is_deleted(
    catalog: MessageCatalog, register: Register
) -> None:
    """The engine purges the profile on opt-out, so the close says so (eval: laura-opt-out)."""
    text = catalog.for_register(register).templates.close_opted_out
    assert re.search(r"(?:borrado|borré) tus datos|deleted your (?:details|data)", text), text


@pytest.mark.parametrize("register", list(Register))
def test_out_of_area_close_makes_no_promise(catalog: MessageCatalog, register: Register) -> None:
    text = (
        catalog.for_register(register)
        .templates.close_disqualified[DisqualificationReason.out_of_area]
        .lower()
    )
    for promise in ("te avisaremos", "te escribiremos", "we'll let you know", "we will contact"):
        assert promise not in text
