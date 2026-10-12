"""T2 of spec 008: the reminder text when a candidate goes quiet (AC-7).

Templates pick up the pending question; the model may rephrase them but must pass the
follow-up guard (end with that question, at most 300 characters), else the template is
sent. Past the WhatsApp window the model is not called at all.
"""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine import ConversationState
from sazon_screening.llm.client.base import FailureKind, Role
from sazon_screening.llm.client.fake import FakeLLMClient, Scripted
from sazon_screening.llm.phrasing.catalog import MessageCatalog
from sazon_screening.llm.phrasing.follow_up import render_follow_up
from sazon_screening.llm.phrasing.guard import Violation, check_follow_up
from sazon_screening.llm.pipeline import ScreeningAgent
from sazon_screening.llm.prompts import PromptRegistry
from sazon_screening.llm.settings import LengthCaps, LLMConfig
from sazon_screening.llm.trace import FollowUpResult
from sazon_screening.vocab import Country, Language, Register, Stage
from tests.engine.builders import Convo
from tests.llm.builders import ctx
from tests.llm.support import FakeClock

AGE_QUESTION = "¿Cuántos años tienes?"
MAX = LengthCaps().default
ASKING_STAGES = [stage for stage in Stage if stage is not Stage.scheduling]


def at(config: EngineConfig, stage: Stage, **kwargs: object) -> ConversationState:
    return Convo(config, **kwargs).advance_to(stage).state  # type: ignore[arg-type]


@pytest.fixture
def agent(
    scripted: FakeLLMClient,
    engine_config: EngineConfig,
    llm_config: LLMConfig,
    catalog: MessageCatalog,
    fake_clock: FakeClock,
) -> ScreeningAgent:
    return ScreeningAgent(
        client=scripted,
        engine_config=engine_config,
        llm_config=llm_config,
        catalog=catalog,
        prompts=PromptRegistry(),
        clock=fake_clock,
        sleep=fake_clock.sleep,
    )


async def remind(
    agent: ScreeningAgent,
    state: ConversationState,
    *,
    step: int = 1,
    kind: str = "nudge",
    requires_template: bool = False,
) -> FollowUpResult:
    return await agent.follow_up(
        state,
        step=step,
        kind=kind,  # type: ignore[arg-type]
        requires_template=requires_template,
        conversation_id="c-1",
    )


# --- the templates -----------------------------------------------------------------------


@pytest.mark.ac("008:AC-7")
def test_the_reminder_picks_up_the_pending_question_and_says_the_progress(
    engine_config: EngineConfig, catalog: MessageCatalog
) -> None:
    text = render_follow_up(
        at(engine_config, Stage.age), "nudge", ctx(), catalog, engine_config, max_chars=MAX
    )
    assert text.question == AGE_QUESTION
    assert text.text.endswith(AGE_QUESTION)
    assert "Solo nos faltan 8 preguntas." in text.text  # age .. start date
    assert len(text.text) <= MAX


@pytest.mark.ac("008:AC-7")
def test_the_last_call_says_it_is_the_last_reminder(
    engine_config: EngineConfig, catalog: MessageCatalog
) -> None:
    text = render_follow_up(
        at(engine_config, Stage.start_date),
        "last_call",
        ctx(),
        catalog,
        engine_config,
        max_chars=MAX,
    )
    assert text.text.startswith("Último recordatorio")
    assert "Solo nos falta una pregunta." in text.text
    assert text.text.endswith("¿Cuándo podrías empezar?")


def test_the_recap_is_not_repeated_in_a_reminder(
    engine_config: EngineConfig, catalog: MessageCatalog
) -> None:
    text = render_follow_up(
        at(engine_config, Stage.recap), "nudge", ctx(), catalog, engine_config, max_chars=MAX
    )
    templates = catalog.for_register(text.register).templates.follow_up
    assert text.question == templates.recap_question
    assert templates.progress_done in text.text


def test_mexico_and_english_use_their_own_register(
    engine_config: EngineConfig, catalog: MessageCatalog
) -> None:
    mexico = at(engine_config, Stage.consent, country_hint=Country.MX)
    text = render_follow_up(mexico, "nudge", ctx(), catalog, engine_config, max_chars=MAX)
    assert text.register is Register.es_MX
    english = at(engine_config, Stage.consent, language=Language.en)
    text = render_follow_up(english, "nudge", ctx(), catalog, engine_config, max_chars=MAX)
    assert (text.register, text.language) == (Register.en, Language.en)
    assert text.text.endswith("?")


def test_a_long_question_drops_the_progress_sentence_to_fit(
    engine_config: EngineConfig, catalog: MessageCatalog
) -> None:
    full = render_follow_up(
        at(engine_config, Stage.age), "last_call", ctx(), catalog, engine_config, max_chars=MAX
    )
    tight = render_follow_up(
        at(engine_config, Stage.age),
        "last_call",
        ctx(),
        catalog,
        engine_config,
        max_chars=len(full.text) - 1,
    )
    assert "preguntas" not in tight.text
    assert tight.text.endswith(AGE_QUESTION)


@pytest.mark.ac("008:AC-7")
@pytest.mark.parametrize("kind", ["nudge", "last_call"])
@pytest.mark.parametrize("stage", ASKING_STAGES, ids=lambda s: s.value)
@pytest.mark.parametrize(
    ("language", "country"),
    [(Language.es, None), (Language.es, Country.MX), (Language.en, None)],
    ids=["es-ES", "es-MX", "en"],
)
def test_every_template_reminder_passes_its_own_guard(
    engine_config: EngineConfig,
    catalog: MessageCatalog,
    stage: Stage,
    kind: str,
    language: Language,
    country: Country | None,
) -> None:
    """The template is the fallback: it must never fail the check it stands in for."""
    state = at(engine_config, stage, language=language, country_hint=country)
    text = render_follow_up(state, kind, ctx(), catalog, engine_config, max_chars=MAX)  # type: ignore[arg-type]
    violations = check_follow_up(
        text.text,
        question=text.question,
        reference=text.text,
        language=text.language,
        ctx=ctx(),
        caps=LengthCaps(),
    )
    assert violations == [], text.text


# --- the model's wording ------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("008:AC-7")
async def test_a_valid_rewording_is_sent(
    agent: ScreeningAgent, scripted: FakeLLMClient, engine_config: EngineConfig
) -> None:
    phrased = f"¿Seguimos? Te quedan 8 preguntas, va rápido. {AGE_QUESTION}"
    scripted.push(Role.phrasing, Scripted(value=phrased))
    result = await remind(agent, at(engine_config, Stage.age), step=2)
    assert result.reply.text == phrased
    assert result.trace.phrasing.outcome == "ok"
    assert (result.trace.follow_up.step, result.trace.follow_up.kind) == (2, "nudge")
    sent = scripted.calls[-1].user
    assert f"<pending_question>{AGE_QUESTION}</pending_question>" in sent
    assert '"is_last": false' in sent


@pytest.mark.anyio
@pytest.mark.ac("008:AC-7")
@pytest.mark.parametrize(
    ("scripted_outcome", "violation"),
    [
        (Scripted(failure=FailureKind.timeout), None),
        (Scripted(failure=FailureKind.refusal), None),
        (Scripted(value="¿Seguimos? ¿Qué edad tienes?"), Violation.pending_question),
        (Scripted(value="¡Hola de nuevo! " + AGE_QUESTION), Violation.repeated_greeting),
        (Scripted(value="Te pagamos 12 € la hora. " + AGE_QUESTION), Violation.pay_or_currency),
        (Scripted(value="x" * 290 + " " + AGE_QUESTION), Violation.too_long),
    ],
    ids=["timeout", "refusal", "question-changed", "greeting", "pay", "too-long"],
)
async def test_a_failed_or_bad_rewording_falls_back_to_the_template(
    agent: ScreeningAgent,
    scripted: FakeLLMClient,
    engine_config: EngineConfig,
    catalog: MessageCatalog,
    scripted_outcome: Scripted,
    violation: Violation | None,
) -> None:
    scripted.push(Role.phrasing, scripted_outcome, scripted_outcome)  # a retry, if any
    state = at(engine_config, Stage.age)
    result = await remind(agent, state)
    template = render_follow_up(state, "nudge", ctx(), catalog, engine_config, max_chars=MAX)
    assert result.reply.text == template.text
    assert result.trace.phrasing.outcome == "fallback"
    if violation is not None:
        assert violation in result.trace.phrasing.violations
    assert len(result.reply.text) <= MAX


@pytest.mark.anyio
@pytest.mark.ac("008:AC-7")
async def test_past_the_window_the_template_is_sent_without_calling_the_model(
    agent: ScreeningAgent, scripted: FakeLLMClient, engine_config: EngineConfig
) -> None:
    result = await remind(
        agent, at(engine_config, Stage.age), step=3, kind="last_call", requires_template=True
    )
    assert scripted.calls == []
    assert result.trace.phrasing.outcome == "skipped"
    assert result.trace.follow_up.requires_template is True
    assert result.reply.text.startswith("Último recordatorio")


@pytest.mark.anyio
async def test_fake_mode_sends_the_template(
    engine_config: EngineConfig, llm_config: LLMConfig, catalog: MessageCatalog
) -> None:
    agent = ScreeningAgent(
        client=FakeLLMClient(mode="rules", engine_config=engine_config),
        engine_config=engine_config,
        llm_config=llm_config,
        catalog=catalog,
        prompts=PromptRegistry(),
    )
    result = await remind(agent, at(engine_config, Stage.age))
    assert result.reply.text.endswith(AGE_QUESTION)
    assert result.trace.phrasing.outcome == "ok"
    assert result.trace.client == "fake-rules"
