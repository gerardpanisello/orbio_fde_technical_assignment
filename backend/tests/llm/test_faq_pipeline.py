"""T3 of spec 009: a candidate's question is answered from the approved FAQ, mid-flow.

The scripted fake checks the guard interplay (what the model wrote vs what was sent);
the rule-based fake runs whole conversations with real retrieval and template replies.
"""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine import AnswerFaq, ConversationState
from sazon_screening.faq import FaqBase, FaqRetriever, load_faq
from sazon_screening.llm.client.base import FailureKind, Role
from sazon_screening.llm.client.fake import FakeLLMClient, Scripted
from sazon_screening.llm.extraction.extractor import InboundMessage, TranscriptEntry
from sazon_screening.llm.extraction.schema import ExtractionOutput
from sazon_screening.llm.phrasing.catalog import MessageCatalog
from sazon_screening.llm.phrasing.guard import Violation
from sazon_screening.llm.pipeline import ScreeningAgent
from sazon_screening.llm.prompts import PromptRegistry
from sazon_screening.llm.settings import LLMConfig
from sazon_screening.llm.trace import TurnContextIn, TurnResult
from sazon_screening.vocab import Country, Language, Register, Stage
from tests.engine.builders import Convo
from tests.llm.conftest import TODAY
from tests.llm.support import FakeClock
from tests.paths import SHIPPED_CONFIG_DIR

SPAIN = TurnContextIn(country_hint=Country.ES)
MEXICO = TurnContextIn(country_hint=Country.MX)
AGE_QUESTION = "¿Cuántos años tienes?"


@pytest.fixture(scope="module")
def faq() -> FaqBase:
    return load_faq(SHIPPED_CONFIG_DIR)


def make_agent(
    client: FakeLLMClient,
    engine_config: EngineConfig,
    llm_config: LLMConfig,
    catalog: MessageCatalog,
    faq: FaqBase | None,
    clock: FakeClock | None = None,
) -> ScreeningAgent:
    clock = clock or FakeClock()
    return ScreeningAgent(
        client=client,
        engine_config=engine_config,
        llm_config=llm_config,
        catalog=catalog,
        prompts=PromptRegistry(),
        faq=faq,
        clock=clock,
        sleep=clock.sleep,
    )


@pytest.fixture
def agent(
    scripted: FakeLLMClient,
    engine_config: EngineConfig,
    llm_config: LLMConfig,
    catalog: MessageCatalog,
    faq: FaqBase,
    fake_clock: FakeClock,
) -> ScreeningAgent:
    return make_agent(scripted, engine_config, llm_config, catalog, faq, fake_clock)


@pytest.fixture
def rules_agent(
    engine_config: EngineConfig, llm_config: LLMConfig, catalog: MessageCatalog, faq: FaqBase
) -> ScreeningAgent:
    client = FakeLLMClient(mode="rules", engine_config=engine_config)
    return make_agent(client, engine_config, llm_config, catalog, faq)


def at_age(config: EngineConfig) -> ConversationState:
    return Convo(config).advance_to(Stage.age).state


async def ask(
    agent: ScreeningAgent,
    scripted: FakeLLMClient,
    state: ConversationState,
    question: str,
    phrased: Scripted,
    context: TurnContextIn = SPAIN,
) -> TurnResult:
    scripted.push(Role.extraction, Scripted(value=ExtractionOutput(faq_question=question)))
    scripted.push(Role.phrasing, phrased)
    return await agent.handle_message(
        state, InboundMessage(text=question), [], today=TODAY, context=context
    )


def approved(faq: FaqBase, entry_id: str, register: Register = Register.es_ES) -> str:
    return faq.entry(entry_id).answer_for(register)


# --- AC-4: answer, then the pending question, in one message ---------------------------


async def converse(
    agent: ScreeningAgent, context: TurnContextIn, messages: list[str], language: Language
) -> list[TurnResult]:
    started = await agent.start_conversation(language=language, context=context)
    state, history, results = started.state, [], [started]
    for text in messages:
        result = await agent.handle_message(
            state, InboundMessage(text=text), history, today=TODAY, context=context
        )
        history.append(TranscriptEntry(role="candidate", text=text))
        if result.reply:
            history.append(TranscriptEntry(role="agent", text=result.reply.text))
        state = result.state
        results.append(result)
    return results


@pytest.mark.anyio
@pytest.mark.ac("009:AC-4")
@pytest.mark.parametrize(
    ("context", "entry", "register"),
    [(SPAIN, "pay-es", Register.es_ES), (MEXICO, "pay-mx", Register.es_MX)],
    ids=["ES", "MX"],
)
async def test_a_question_mid_flow_is_answered_and_the_ask_resumes(
    rules_agent: ScreeningAgent,
    faq: FaqBase,
    context: TurnContextIn,
    entry: str,
    register: Register,
) -> None:
    """Fake mode: real retrieval, the approved text verbatim, then the same question."""
    results = await converse(
        rules_agent, context, ["sí, acepto", "Me llamo Ana López", "¿cuánto se paga?"], Language.es
    )
    before, answered = results[-2], results[-1]
    assert before.reply is not None
    assert answered.reply is not None
    assert answered.trace.faq is not None
    assert answered.trace.faq.outcome == "answered"
    assert answered.trace.faq.entry_ids == [entry]
    text = answered.reply.text
    assert text.startswith(approved(faq, entry, register))
    assert text.endswith(AGE_QUESTION)  # the pending ask, in the same message
    assert answered.state.stage is Stage.age
    assert len(text) <= 600


@pytest.mark.anyio
@pytest.mark.ac("009:AC-4")
async def test_an_english_question_about_the_bike_is_answered(
    rules_agent: ScreeningAgent, faq: FaqBase
) -> None:
    results = await converse(
        rules_agent, SPAIN, ["yes", "Anna Smith", "do I need my own bike?"], Language.en
    )
    last = results[-1]
    assert last.trace.faq is not None
    assert last.trace.faq.entry_ids == ["vehicle-own"]
    assert last.reply is not None
    assert last.reply.text.startswith(approved(faq, "vehicle-own", Register.en))
    assert last.reply.text.endswith("?")


@pytest.mark.anyio
async def test_unknown_country_answers_generally(
    agent: ScreeningAgent, scripted: FakeLLMClient, engine_config: EngineConfig, faq: FaqBase
) -> None:
    result = await ask(
        agent,
        scripted,
        at_age(engine_config),
        "¿cuánto se paga?",
        Scripted(failure=FailureKind.refusal),
        TurnContextIn(),
    )
    assert result.trace.faq is not None
    assert result.trace.faq.entry_ids == ["pay-general"]
    assert result.reply is not None
    assert result.reply.text.startswith(approved(faq, "pay-general"))


# --- the model's wording and the guard ---------------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("009:AC-4")
async def test_the_model_answers_from_the_approved_entry(
    agent: ScreeningAgent, scripted: FakeLLMClient, engine_config: EngineConfig, faq: FaqBase
) -> None:
    phrased = f"Se paga entre 9 y 12 € brutos la hora, según la ciudad. {AGE_QUESTION}"
    result = await ask(
        agent, scripted, at_age(engine_config), "¿cuánto se paga?", Scripted(value=phrased)
    )
    assert f"<faq_answer>{approved(faq, 'pay-es')}</faq_answer>" in scripted.calls[-1].user
    assert result.trace.phrasing.outcome == "ok"
    assert result.reply is not None
    assert result.reply.text == phrased


@pytest.mark.anyio
@pytest.mark.ac("009:AC-5")
@pytest.mark.parametrize(
    "invented",
    [
        f"Se paga 15 € la hora. {AGE_QUESTION}",  # an amount the entry never says
        f"Se paga entre 9 y 12 euros la hora. {AGE_QUESTION}",  # another currency word
        f"Se paga entre 9 y 12 € la hora, unos 1.800 al mes. {AGE_QUESTION}",  # a sum
    ],
    ids=["amount", "currency-word", "derived-total"],
)
async def test_an_invented_amount_fails_the_guard_and_the_approved_text_is_sent(
    agent: ScreeningAgent,
    scripted: FakeLLMClient,
    engine_config: EngineConfig,
    faq: FaqBase,
    invented: str,
) -> None:
    result = await ask(
        agent, scripted, at_age(engine_config), "¿cuánto se paga?", Scripted(value=invented)
    )
    assert Violation.pay_or_currency in result.trace.phrasing.violations
    assert result.trace.phrasing.outcome == "fallback"
    assert result.reply is not None
    # The approved answer verbatim, then the pending question: not "lo consulto".
    assert result.reply.text == f"{approved(faq, 'pay-es')} {AGE_QUESTION}"
    assert result.trace.faq is not None
    assert result.trace.faq.outcome == "answered"


# --- AC-3: nothing approved to say --------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("009:AC-3")
async def test_an_unrelated_question_gets_the_holding_message_and_is_flagged(
    agent: ScreeningAgent,
    scripted: FakeLLMClient,
    engine_config: EngineConfig,
    catalog: MessageCatalog,
) -> None:
    question = "¿cuál es la capital de Francia?"
    result = await ask(
        agent, scripted, at_age(engine_config), question, Scripted(failure=FailureKind.refusal)
    )
    holding = catalog.for_register(Register.es_ES).templates.prefaces.faq_holding
    assert result.reply is not None
    assert result.reply.text == f"{holding} {AGE_QUESTION}"
    assert "<faq_answer>" not in scripted.calls[-1].user
    faq = result.trace.faq
    assert faq is not None
    assert faq.outcome == "unanswered"
    assert (faq.question, faq.entry_ids, faq.country) == (question, [], Country.ES)


@pytest.mark.anyio
async def test_without_a_knowledge_base_every_question_is_flagged(
    scripted: FakeLLMClient,
    engine_config: EngineConfig,
    llm_config: LLMConfig,
    catalog: MessageCatalog,
) -> None:
    agent = make_agent(scripted, engine_config, llm_config, catalog, faq=None)
    result = await ask(
        agent,
        scripted,
        at_age(engine_config),
        "¿cuánto se paga?",
        Scripted(failure=FailureKind.refusal),
    )
    assert result.trace.faq is not None
    assert result.trace.faq.outcome == "unanswered"


@pytest.mark.anyio
async def test_a_retrieval_bug_holds_and_flags_instead_of_crashing(
    agent: ScreeningAgent,
    scripted: FakeLLMClient,
    engine_config: EngineConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*_: object) -> None:
        raise KeyError("boom")

    monkeypatch.setattr(FaqRetriever, "search", broken)
    result = await ask(
        agent,
        scripted,
        at_age(engine_config),
        "¿cuánto se paga?",
        Scripted(failure=FailureKind.refusal),
    )
    assert result.reply is not None
    assert result.reply.text.endswith(AGE_QUESTION)
    assert result.trace.faq is not None
    assert (result.trace.faq.outcome, result.trace.faq.error) == ("unanswered", "KeyError")


@pytest.mark.anyio
async def test_no_question_no_faq_trace(
    agent: ScreeningAgent, scripted: FakeLLMClient, engine_config: EngineConfig
) -> None:
    scripted.push(Role.extraction, Scripted(value=ExtractionOutput()))
    scripted.push(Role.phrasing, Scripted(failure=FailureKind.refusal))
    result = await agent.handle_message(
        at_age(engine_config), InboundMessage(text="mmm"), [], today=TODAY, context=SPAIN
    )
    assert result.trace.faq is None
    assert result.trace.action is not None
    assert AnswerFaq() not in result.trace.action.prefaces
