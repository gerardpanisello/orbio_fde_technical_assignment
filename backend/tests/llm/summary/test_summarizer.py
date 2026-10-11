"""T23: the recruiter summary - facts by code, narrative by the model (FR-18..22)."""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine import CandidateRecord
from sazon_screening.llm.client.base import FailureKind, Role
from sazon_screening.llm.client.fake import FakeLLMClient, Scripted
from sazon_screening.llm.extraction.extractor import TranscriptEntry
from sazon_screening.llm.phrasing.catalog import MessageCatalog
from sazon_screening.llm.prompts import PromptRegistry
from sazon_screening.llm.settings import LLMConfig
from sazon_screening.llm.summary.facts import render_facts
from sazon_screening.llm.summary.summarizer import NarrativeOutput, Summarizer, summary_due
from sazon_screening.vocab import Language, Status
from tests.engine.builders import Convo, name
from tests.llm.support import FakeClock

NARRATIVE = NarrativeOutput(
    overview="Candidata con experiencia en reparto; dice estar disponible de inmediato.",
    sentiment="positive",
    sentiment_reason="Respuestas rápidas y amables.",
    observations=["Preguntó por el uniforme."],
)
TRANSCRIPT = [
    TranscriptEntry(role="agent", text="¿Cómo te llamas?"),
    TranscriptEntry(role="candidate", text="Ana López"),
]


@pytest.fixture
def summarizer(
    scripted: FakeLLMClient,
    llm_config: LLMConfig,
    catalog: MessageCatalog,
    prompts: PromptRegistry,
    engine_config: EngineConfig,
    fake_clock: FakeClock,
) -> Summarizer:
    return Summarizer(
        client=scripted,
        config=llm_config,
        catalog=catalog,
        prompts=prompts,
        engine_config=engine_config,
        clock=fake_clock,
        sleep=fake_clock.sleep,
    )


def record_for(status: Status, config: EngineConfig) -> CandidateRecord:
    return Convo(config).advance_to_status(status).record()


@pytest.mark.anyio
@pytest.mark.ac("003:AC-17")
async def test_narrative_and_facts(
    summarizer: Summarizer,
    scripted: FakeLLMClient,
    catalog: MessageCatalog,
    engine_config: EngineConfig,
) -> None:
    scripted.push(Role.summary, Scripted(value=NARRATIVE))
    record = record_for(Status.interview_scheduled, engine_config)
    summary, calls = await summarizer.summarise(record, TRANSCRIPT)
    assert summary.generated_by == "llm"
    assert summary.narrative == NARRATIVE
    assert summary.facts == render_facts(record, Language.es, catalog, engine_config)
    assert (summary.status, summary.language, summary.candidate_language) == (
        Status.interview_scheduled,
        Language.es,
        record.language,
    )
    assert summary.prompt_id == "summary.v1"
    assert NARRATIVE.overview in summary.text
    assert "**Estado:** Entrevista agendada" in summary.text
    assert [call.role for call in calls] == [Role.summary]


@pytest.mark.anyio
async def test_the_record_and_transcript_are_data_in_the_request(
    summarizer: Summarizer, scripted: FakeLLMClient, engine_config: EngineConfig
) -> None:
    scripted.push(Role.summary, Scripted(value=NARRATIVE))
    await summarizer.summarise(record_for(Status.disqualified, engine_config), TRANSCRIPT)
    request = scripted.calls[0]
    assert '"status":"disqualified"' in request.user
    assert "<candidate>Ana López</candidate>" in request.user
    assert "Ana López" not in request.system


@pytest.mark.anyio
async def test_the_transcript_is_cut_to_the_configured_size(
    summarizer: Summarizer,
    scripted: FakeLLMClient,
    engine_config: EngineConfig,
    llm_config: LLMConfig,
) -> None:
    scripted.push(Role.summary, Scripted(value=NARRATIVE))
    long = [TranscriptEntry(role="candidate", text=f"línea {i} " + "x" * 100) for i in range(200)]
    await summarizer.summarise(record_for(Status.abandoned, engine_config), long)
    user = scripted.calls[0].user
    transcript = user[user.index("<transcript>") : user.index("</transcript>")]
    assert len(transcript) <= llm_config.summary_max_transcript_chars + len("<transcript>") + 1
    assert "línea 199" in transcript
    assert "línea 0 " not in transcript


@pytest.mark.anyio
@pytest.mark.ac("003:AC-18")
async def test_opted_out_makes_no_call_and_holds_no_personal_data(
    summarizer: Summarizer, scripted: FakeLLMClient, engine_config: EngineConfig
) -> None:
    convo = Convo(engine_config).advance_to_status(Status.in_progress)
    convo.say(name("Ana López")).say(opt_out=True)
    summary, calls = await summarizer.summarise(convo.record(), TRANSCRIPT)
    assert scripted.calls == []
    assert calls == []
    assert summary.generated_by == "template"
    assert "Ana" not in summary.text


@pytest.mark.anyio
@pytest.mark.ac("003:AC-19")
async def test_a_failed_call_gives_the_facts_only(
    summarizer: Summarizer, scripted: FakeLLMClient, engine_config: EngineConfig
) -> None:
    scripted.push(Role.summary, Scripted(failure=FailureKind.refusal))
    summary, _ = await summarizer.summarise(record_for(Status.needs_review, engine_config), [])
    assert summary.generated_by == "template"
    assert summary.narrative is None
    assert summary.facts
    assert "Requiere revisión" in summary.text


@pytest.mark.anyio
async def test_the_recruiter_can_ask_for_english(
    summarizer: Summarizer, scripted: FakeLLMClient, engine_config: EngineConfig
) -> None:
    scripted.push(Role.summary, Scripted(value=NARRATIVE))
    record = record_for(Status.qualified_unscheduled, engine_config)
    summary, _ = await summarizer.summarise(record, TRANSCRIPT, Language.en)
    assert summary.language is Language.en
    assert "**Status:** Qualified, not scheduled" in summary.text
    assert "<recruiter_language>en</recruiter_language>" in scripted.calls[0].user


@pytest.mark.ac("003:AC-20")
@pytest.mark.parametrize(
    ("previous", "new", "due"),
    [
        (Status.in_progress, Status.abandoned, True),
        (Status.abandoned, Status.in_progress, False),
        (Status.abandoned, Status.interview_scheduled, True),
        (Status.disqualified, Status.needs_review, True),
        (Status.disqualified, Status.disqualified, False),
        (None, Status.in_progress, False),
        (Status.in_progress, Status.opted_out, True),
    ],
)
def test_summary_due(previous: Status | None, new: Status, due: bool) -> None:
    assert summary_due(previous, new) is due
