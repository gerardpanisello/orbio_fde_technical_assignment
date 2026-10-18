"""Spec 017: Catalan as a third candidate language, offline (rules agent, network blocked).

The live checks (real model) are in the spec notes; these pin what code owns: the
register, the templates and their fallback, the guard, the extraction mapping and the
FAQ in Catalan, and that Spanish and English behave as before.
"""

import json
from typing import Any

import pytest

from sazon_screening.config import EngineConfig, load_config
from sazon_screening.engine import AskField, CloseDisqualified, TurnContext, register_for
from sazon_screening.faq import FaqBase, load_faq
from sazon_screening.llm.client.base import Role
from sazon_screening.llm.client.fake import FakeLLMClient, Scripted
from sazon_screening.llm.client.fake_rules import RuleExtractor
from sazon_screening.llm.extraction.extractor import InboundMessage
from sazon_screening.llm.extraction.mapping import to_turn_input
from sazon_screening.llm.extraction.schema import ExtractionOutput
from sazon_screening.llm.phrasing.catalog import MessageCatalog
from sazon_screening.llm.phrasing.guard import Violation, check
from sazon_screening.llm.phrasing.language import dominant_language
from sazon_screening.llm.phrasing.phraser import LAST_RESORT
from sazon_screening.llm.phrasing.templates import render_template
from sazon_screening.llm.pipeline import ScreeningAgent
from sazon_screening.llm.prompts import PromptRegistry
from sazon_screening.llm.settings import LengthCaps, LLMConfig
from sazon_screening.llm.trace import TurnContextIn
from sazon_screening.vocab import (
    Country,
    DisqualificationReason,
    FieldName,
    Language,
    Register,
    Stage,
    Status,
)
from tests.engine.builders import Convo
from tests.llm.builders import SLOTS, action, asking, ctx, sample_primaries
from tests.llm.chat import Chat
from tests.llm.conftest import TODAY
from tests.paths import BACKEND_DIR, FIXTURE_CONFIG_DIR, SHIPPED_CONFIG_DIR

SPANISH_PHONE = TurnContextIn(country_hint=Country.ES, slots=list(SLOTS.values()))
CATALAN_SCRIPT = [
    "sí, d'acord",
    "Em dic Jordi Puig",
    "tinc 24 anys",
    "cotxe",
    "sí",
    "visc a Chamberí, Madrid",
    "mitja jornada",
    "a la tarda",
    "2 anys a Glovo",
    "dilluns",
    "sí, tot correcte",
    "la 1",
]


def _agent(
    client: FakeLLMClient,
    engine_config: EngineConfig,
    llm_config: LLMConfig,
    catalog: MessageCatalog,
    faq: FaqBase | None = None,
) -> ScreeningAgent:
    return ScreeningAgent(
        client=client,
        engine_config=engine_config,
        llm_config=llm_config,
        catalog=catalog,
        prompts=PromptRegistry(),
        faq=faq,
    )


@pytest.fixture
def catalan_chat(
    engine_config: EngineConfig, llm_config: LLMConfig, catalog: MessageCatalog
) -> Chat:
    client = FakeLLMClient(mode="rules", engine_config=engine_config)
    agent = _agent(client, engine_config, llm_config, catalog, load_faq(SHIPPED_CONFIG_DIR))
    return Chat(agent=agent, llm_config=llm_config, context=SPANISH_PHONE)


def _sofi(chat: Chat) -> list[str]:
    return [r.reply.text for r in chat.results if r.reply is not None and r.reply.text]


# --- AC-1: a whole screening in Catalan -------------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("017:AC-1")
async def test_a_whole_screening_in_catalan_reaches_an_interview(catalan_chat: Chat) -> None:
    await catalan_chat.start(language=Language.ca)
    for text in CATALAN_SCRIPT:
        await catalan_chat.say(text)
    state = catalan_chat.state
    assert state is not None
    assert state.status is Status.interview_scheduled, _sofi(catalan_chat)
    assert state.selected_slot_id == "s1"
    replies = [r.reply for r in catalan_chat.results if r.reply is not None]
    assert all(reply.language is Language.ca for reply in replies)
    assert all(reply.register is Register.ca_ES for reply in replies)
    for text in _sofi(catalan_chat):
        assert dominant_language(text) in (None, Language.ca), text
    joined = " ".join(_sofi(catalan_chat))
    assert "dimarts 14/10, 10:00" in joined  # the slot in Catalan, not "martes"
    assert "carnet de conduir" in joined
    record = state.profile
    assert record.age.value is not None
    assert record.age.value.age == 24


# --- AC-2: switching from Spanish to Catalan mid-conversation ---------------------------


@pytest.mark.anyio
@pytest.mark.ac("017:AC-2")
async def test_switching_from_spanish_to_catalan_keeps_the_data(catalan_chat: Chat) -> None:
    await catalan_chat.start(language=Language.es)
    await catalan_chat.say("sí, acepto")
    spanish = await catalan_chat.say("Me llamo Ana López")
    assert spanish.reply is not None
    assert spanish.reply.language is Language.es
    switched = await catalan_chat.say("tinc 25 anys")
    assert switched.reply is not None
    assert switched.reply.language is Language.ca
    assert switched.reply.register is Register.ca_ES
    after = await catalan_chat.say("cotxe")  # a button label keeps the language
    assert after.reply is not None
    assert after.reply.language is Language.ca
    state = catalan_chat.state
    assert state is not None
    assert state.profile.full_name.value == "Ana López"
    assert state.profile.age.value is not None
    assert state.profile.age.value.age == 25
    assert state.language is Language.ca


@pytest.mark.anyio
@pytest.mark.ac("017:AC-2")
async def test_back_from_catalan_to_spanish(catalan_chat: Chat) -> None:
    await catalan_chat.start(language=Language.ca)
    await catalan_chat.say("sí, d'acord")
    back = await catalan_chat.say("Me llamo Ana López y tengo 25 años")
    assert back.reply is not None
    assert back.reply.language is Language.es


# --- AC-3: the catalog, the guard and the fallback --------------------------------------


@pytest.mark.ac("017:AC-3")
def test_the_catalan_catalog_covers_every_template(catalog: MessageCatalog) -> None:
    entry = catalog.for_register(Register.ca_ES)
    assert entry.register is Register.ca_ES
    assert catalog.for_language(Language.ca) is entry
    assert entry.summary is None  # recruiters read es/en (FR-6)
    for key, text in entry.templates.texts():
        assert dominant_language(text) in (None, Language.ca), f"{key}: {text}"
    assert entry.labels.fields[FieldName.has_license] == "carnet de conduir"
    assert entry.labels.from_month.format(month=entry.labels.months[10]) == "a partir d'octubre"
    assert entry.labels.from_month.format(month=entry.labels.months[11]) == "a partir de novembre"


@pytest.mark.ac("017:AC-3")
@pytest.mark.parametrize(
    "primary", sample_primaries(load_config(FIXTURE_CONFIG_DIR)), ids=lambda p: p.type
)
def test_every_catalan_template_passes_the_guard_in_catalan(
    catalog: MessageCatalog, engine_config: EngineConfig, primary: Any
) -> None:
    act = action(primary, register=Register.ca_ES)
    text = render_template(act, ctx(), catalog, engine_config)
    assert check(text, act, ctx(), LengthCaps()) == [], text
    assert dominant_language(text) != Language.es, text


@pytest.mark.ac("017:AC-3")
def test_the_last_resort_message_is_catalan() -> None:
    assert dominant_language(LAST_RESORT[Language.ca] + " Perdona, ho sento molt.") in (
        None,
        Language.ca,
    )
    assert "tingut" in LAST_RESORT[Language.ca]


@pytest.mark.anyio
@pytest.mark.ac("017:AC-3")
async def test_a_spanish_reply_in_a_catalan_chat_falls_back_to_the_catalan_template(
    scripted: FakeLLMClient,
    engine_config: EngineConfig,
    llm_config: LLMConfig,
    catalog: MessageCatalog,
) -> None:
    agent = _agent(scripted, engine_config, llm_config, catalog)
    state = Convo(engine_config).advance_to(Stage.age).state
    state = state.model_copy(update={"language": Language.ca})
    scripted.push(Role.extraction, Scripted(value=ExtractionOutput(age=25, language="ca")))
    scripted.push(
        Role.phrasing,
        Scripted(value="Perfecto, gracias. ¿Con qué vehículo te gustaría repartir con nosotros?"),
    )
    result = await agent.handle_message(
        state, InboundMessage(text="tinc 25 anys"), [], today=TODAY, context=SPANISH_PHONE
    )
    assert result.reply is not None
    assert result.trace.phrasing is not None
    assert Violation.wrong_language in result.trace.phrasing.violations
    assert result.reply.text == "Amb quin vehicle repartiries?"


@pytest.mark.ac("017:AC-3")
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Perfecte! Amb quin vehicle repartiries? Tens el carnet de conduir en vigor?", "ca"),
        ("Gràcies, Jordi. I a quin barri de la ciutat vols repartir amb nosaltres?", "ca"),
        ("Hi ha diversos llocs amb aquest nom. Quin és el teu?", "ca"),
        ("Perfecto, gracias. ¿Con qué vehículo te gustaría repartir con nosotros?", "es"),
        ("Thanks! Which vehicle would you deliver with, and do you have a licence?", "en"),
        ("Quants anys tens?", None),  # too short to tell: never rejected
        ("¡Genial, Ana! ¿Tienes Glovo?", None),
    ],
)
def test_the_language_check_tells_catalan_from_spanish(text: str, expected: str | None) -> None:
    found = dominant_language(text)
    assert (found.value if found else None) == expected


@pytest.mark.ac("017:AC-3")
def test_catalan_greeting_and_masculine_forms_are_caught(engine_config: EngineConfig) -> None:
    ask = action(AskField(field=FieldName.age), register=Register.ca_ES)
    assert Violation.repeated_greeting in check(
        "Bona tarda! Quants anys tens?", ask, ctx(), LengthCaps()
    )
    assert Violation.masculine_form in check(
        "Encantat de conèixer-te. Quants anys tens?", ask, ctx(), LengthCaps()
    )
    assert check("Encantada, Jordi. Quants anys tens?", ask, ctx(), LengthCaps()) == []
    close = action(
        CloseDisqualified(reason=DisqualificationReason.no_license), register=Register.ca_ES
    )
    hi_ha = "Hi ha una cosa: per a aquesta feina cal tenir el carnet de conduir en vigor."
    assert Violation.repeated_greeting not in check(hi_ha, close, ctx(), LengthCaps())


# --- AC-4: a Catalan question about the job ---------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("017:AC-4")
async def test_a_catalan_pay_question_is_answered_in_catalan(catalan_chat: Chat) -> None:
    faq = load_faq(SHIPPED_CONFIG_DIR)
    # Driven without Chat: its re-check has no FAQ grounding, and money talk needs it.
    agent = catalan_chat.agent
    started = await agent.start_conversation(language=Language.ca, context=SPANISH_PHONE)
    state = started.state
    for text in ("sí, d'acord", "Em dic Jordi Puig"):
        message = InboundMessage(text=text)
        state = (await agent.handle_message(state, message, [], today=TODAY)).state
    question = InboundMessage(text="quant es cobra?")
    answered = await agent.handle_message(state, question, [], today=TODAY, context=SPANISH_PHONE)
    assert answered.trace.faq is not None
    assert answered.trace.faq.outcome == "answered"
    assert answered.trace.faq.entry_ids == ["pay-es"]
    assert answered.trace.faq.entry_question == "¿Cuánto se paga?"  # recruiters read es
    assert answered.reply is not None
    text = answered.reply.text
    assert text.startswith(faq.entry("pay-es").answer_for(Register.ca_ES))
    assert text.endswith("Quants anys tens?")


@pytest.mark.ac("017:AC-4")
def test_every_faq_entry_has_a_catalan_answer_and_questions() -> None:
    faq = load_faq(SHIPPED_CONFIG_DIR)
    for entry in faq.entries:
        assert len(entry.questions[Language.ca]) >= 2, entry.id
        answer = entry.answer[Register.ca_ES]
        assert answer != entry.answer[Register.es_ES]
        assert dominant_language(answer) != Language.es, (entry.id, answer)


# --- AC-5: extraction ---------------------------------------------------------------------


@pytest.mark.ac("017:AC-5")
def test_the_wire_schema_offers_catalan() -> None:
    schema = ExtractionOutput.model_json_schema(mode="serialization")
    assert schema["properties"]["language"]["enum"] == ["", "es", "en", "ca"]
    assert ExtractionOutput.model_validate({"language": "ca"}).language == "ca"


@pytest.mark.ac("017:AC-5")
def test_a_catalan_message_switches_the_language() -> None:
    mapped = to_turn_input(
        ExtractionOutput(age=24, language="ca"),
        asking(FieldName.age),
        TurnContext(),
        text="tinc 24 anys",
    )
    assert mapped.turn_input.signals.language is Language.ca  # type: ignore[union-attr]


@pytest.mark.ac("017:AC-5")
def test_a_name_alone_keeps_the_language_even_if_the_model_says_catalan() -> None:
    mapped = to_turn_input(
        ExtractionOutput(full_name="Jordi Puig", language="ca"),
        asking(FieldName.full_name),
        TurnContext(),
        text="Jordi Puig",
    )
    assert mapped.turn_input.signals.language is None  # type: ignore[union-attr]


NEXT_MONTH = {"start_kind": "offset", "start_offset_amount": 1, "start_offset_unit": "months"}


@pytest.mark.ac("017:AC-5")
@pytest.mark.parametrize(
    ("text", "field", "expected"),
    [
        ("sí, d'acord", FieldName.consent, {"consent": "yes", "language": "ca"}),
        ("tinc 24 anys", FieldName.age, {"age": 24, "language": "ca"}),
        ("cotxe", FieldName.vehicle_type, {"vehicle_type": "car"}),
        ("tinc el carnet de conduir", FieldName.has_license, {"has_license": True}),
        ("visc a Chamberí", FieldName.location, {"location_zone": "Chamberí"}),
        (
            "mitja jornada i caps de setmana",
            FieldName.availability,
            {"availability": ["part_time", "weekends"]},
        ),
        ("a la tarda", FieldName.schedule, {"schedule": ["afternoon"], "language": "ca"}),
        ("2 anys a Glovo", FieldName.experience, {"experience_years": 2, "platforms": ["glovo"]}),
        ("el mes que ve", FieldName.start_date, NEXT_MONTH),
        ("dilluns", FieldName.start_date, {"start_kind": "next_weekday", "start_weekday": "mon"}),
        (
            "el 3 de novembre",
            FieldName.start_date,
            {"start_kind": "day_month", "start_day": 3, "start_month": 11},
        ),
        ("a partir de novembre", FieldName.start_date, {"start_kind": "month", "start_month": 11}),
    ],
)
def test_the_offline_extractor_reads_typical_catalan_answers(
    engine_config: EngineConfig, text: str, field: FieldName, expected: dict[str, Any]
) -> None:
    extracted = RuleExtractor(engine_config).extract(text, asking(field))
    dumped = extracted.model_dump()
    assert {key: dumped[key] for key in expected} == expected


@pytest.mark.ac("017:AC-5")
def test_the_extraction_prompt_gives_catalan_cues() -> None:
    from sazon_screening.llm.settings import load_llm_config

    prompt_id = load_llm_config(SHIPPED_CONFIG_DIR).roles[Role.extraction].prompt
    text = PromptRegistry().load(prompt_id).text
    for cue in ('"ca" (Catalan)', '"tinc"', '"visc"', "d'acord", '"vull"', "a la tarda"):
        assert cue in text, cue


# --- AC-6: Spanish and English unchanged --------------------------------------------------


@pytest.mark.ac("017:AC-6")
@pytest.mark.parametrize(
    ("language", "country", "expected"),
    [
        (Language.es, Country.ES, Register.es_ES),
        (Language.es, Country.MX, Register.es_MX),
        (Language.en, Country.MX, Register.en),
        (Language.ca, Country.ES, Register.ca_ES),
        (Language.ca, Country.MX, Register.ca_ES),
    ],
)
def test_registers(language: Language, country: Country, expected: Register) -> None:
    assert register_for(language, country, None, default_country=Country.ES) is expected
    assert expected.language is language


@pytest.mark.ac("017:AC-6")
def test_the_committed_record_schema_lists_catalan() -> None:
    path = BACKEND_DIR.parent / "docs/specs/002-screening-engine/candidate-record.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    assert schema["$defs"]["Language"]["enum"] == ["es", "en", "ca"]


@pytest.mark.ac("017:AC-6")
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Perfecto, gracias. ¿Con qué vehículo te gustaría repartir?", "es"),
        ("Thanks! Which vehicle would you deliver with?", "en"),
        ("Vale", None),
    ],
)
def test_spanish_and_english_detection_is_unchanged(text: str, expected: str | None) -> None:
    found = dominant_language(text)
    assert (found.value if found else None) == expected


@pytest.mark.ac("017:AC-6")
def test_place_names_fall_back_to_spanish_for_catalan(engine_config: EngineConfig) -> None:
    madrid = next(c for c in engine_config.service_areas.countries[0].cities if c.id == "madrid")
    assert madrid.names[Language.ca] == madrid.names[Language.es]
    assert SLOTS["s1"].label(Language.ca) == "dimarts 14/10, 10:00"


@pytest.mark.ac("017:AC-6")
def test_recruiter_summaries_stay_spanish_or_english(catalog: MessageCatalog) -> None:
    with pytest.raises(ValueError, match="es or en"):
        catalog.summary_labels(Language.ca)
    assert catalog.summary_labels(Language.es).languages[Language.ca] == "Catalán"
    assert catalog.summary_labels(Language.en).languages[Language.ca] == "Catalan"


@pytest.mark.ac("017:AC-3")
def test_the_phrasing_prompt_writes_natural_catalan() -> None:
    from sazon_screening.llm.settings import load_llm_config

    prompt_id = load_llm_config(SHIPPED_CONFIG_DIR).roles[Role.phrasing].prompt
    text = PromptRegistry().load(prompt_id).text
    for cue in ("ca-ES (Catalan)", '"encantat"', "carnet de conduir", "l'entrevista", "la teva"):
        assert cue in text, cue


@pytest.mark.ac("017:AC-3")
def test_a_greeting_without_the_automated_disclosure_falls_back(catalog: MessageCatalog) -> None:
    """Live check 017: the model once dropped "(automàtica)" from the Catalan greeting."""
    act = action(AskField(field=FieldName.consent), register=Register.ca_ES)
    greeting = ctx(is_greeting=True)
    url = greeting.privacy_url
    dropped = (
        "Hola! Sóc la Sofi, l'assistent virtual de Grupo Sazón. Et faré unes preguntes "
        f"ràpides. Política de privacitat: {url} Acceptes que fem servir les teves dades?"
    )
    kept = dropped.replace("virtual de", "virtual (automàtica) de")
    assert Violation.missing_disclosure in check(dropped, act, greeting, LengthCaps())
    assert check(kept, act, greeting, LengthCaps()) == []
    no_link = kept.replace(url, "")
    assert Violation.missing_disclosure in check(no_link, act, greeting, LengthCaps())
