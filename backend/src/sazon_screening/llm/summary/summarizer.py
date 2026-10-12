"""The recruiter summary of a finished conversation (FR-18..22).

Two parts on purpose: facts rendered by code from the record (the source of truth),
and a short narrative from the model (tone, questions asked, constraints mentioned).
If the model fails, the summary is the facts alone. An opted-out candidate gets no
model call and no transcript at all (FR-21, GDPR/LFPDPPP).
"""

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Literal

import anyio
from pydantic import BaseModel, ConfigDict, Field

from sazon_screening.config import EngineConfig
from sazon_screening.engine import CandidateRecord
from sazon_screening.llm.client.base import LLMClient, LLMRequest, Role
from sazon_screening.llm.client.retry import Clock, Deadline, SystemClock, call_with_retry
from sazon_screening.llm.delimit import tagged
from sazon_screening.llm.extraction.extractor import TranscriptEntry
from sazon_screening.llm.phrasing.catalog import MessageCatalog, SummaryLabels
from sazon_screening.llm.prompts import PromptRegistry
from sazon_screening.llm.settings import LLMConfig
from sazon_screening.llm.summary.facts import SummaryFact, render_facts
from sazon_screening.llm.telemetry import CallTelemetry, log_call, telemetry_from
from sazon_screening.vocab import Language, Status

logger = logging.getLogger("sazon_screening.llm")
TERMINAL = frozenset(
    {
        Status.interview_scheduled,
        Status.qualified_unscheduled,
        Status.waitlisted,
        Status.disqualified,
        Status.needs_review,
        Status.abandoned,
        Status.opted_out,
    }
)


class NarrativeOutput(BaseModel):
    """What the summary model fills. Claims stay claims; the record is never restated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    overview: str = Field(
        description="At most 3 sentences. Candidate statements are claims, not facts."
    )
    sentiment: Literal["positive", "neutral", "negative"] = Field(
        description="The candidate's overall tone in the conversation."
    )
    sentiment_reason: str = Field(description="One short line explaining the sentiment.")
    observations: list[str] = Field(
        description="At most 4 short notes a recruiter should know (questions, constraints)."
    )


class SummaryPayload(BaseModel):
    """Structured input for the rule-based fake (never sent to the API)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Status
    language: Language


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    language: Language  # the recruiter's language
    candidate_language: Language
    status: Status
    facts: list[SummaryFact]
    narrative: NarrativeOutput | None
    generated_by: Literal["llm", "template"]
    prompt_id: str | None
    model: str | None
    text: str  # markdown for the dashboard: facts, then the narrative


def summary_due(previous: Status | None, new: Status) -> bool:
    """A summary is (re)generated whenever the status becomes a different terminal one."""
    return new in TERMINAL and new is not previous


class Summarizer:
    def __init__(
        self,
        *,
        client: LLMClient,
        config: LLMConfig,
        catalog: MessageCatalog,
        prompts: PromptRegistry,
        engine_config: EngineConfig,
        clock: Clock | None = None,
        sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
    ) -> None:
        self._client = client
        self._config = config
        self._catalog = catalog
        self._engine_config = engine_config
        self._role = config.roles[Role.summary]
        self._prompt = prompts.load(self._role.prompt)
        self._clock = clock or SystemClock()
        self._sleep = sleep

    async def summarise(
        self,
        record: CandidateRecord,
        transcript: Sequence[TranscriptEntry],
        language: Language | None = None,
        *,
        conversation_id: str | None = None,
    ) -> tuple[Summary, list[CallTelemetry]]:
        language = language or self._config.summary_default_language
        facts = render_facts(record, language, self._catalog, self._engine_config)
        if record.status is Status.opted_out:  # FR-21: nothing about the person goes out
            return self._summary(record, language, facts, None), []
        request = self._request(record, transcript, language)
        # Not on the candidate's clock (004 runs it after replying): room for every retry.
        budget = self._role.timeout_s * self._config.retry.max_attempts + 5
        result = await call_with_retry(
            lambda t: self._client.parse(
                request.model_copy(update={"timeout_s": t}), NarrativeOutput
            ),
            role_timeout_s=self._role.timeout_s,
            deadline=Deadline(self._clock, budget),
            policy=self._config.retry,
            sleep=self._sleep,
        )
        telemetry = telemetry_from(request, result, self._config.prices)
        log_call(telemetry, conversation_id=conversation_id)
        narrative = result.value if result.ok else None
        return self._summary(record, language, facts, narrative), [telemetry]

    def _request(
        self, record: CandidateRecord, transcript: Sequence[TranscriptEntry], language: Language
    ) -> LLMRequest:
        lines = "\n".join(tagged(entry.role, entry.text) for entry in transcript)
        recent = lines[-self._config.summary_max_transcript_chars :]
        user = "\n".join(
            [
                f"<recruiter_language>{language.value}</recruiter_language>",
                f"<record>{record.model_dump_json()}</record>",
                f"<transcript>{recent}</transcript>",
            ]
        )
        return LLMRequest(
            role=Role.summary,
            model=self._role.model,
            prompt_id=self._prompt.id,
            prompt_sha=self._prompt.sha,
            system=self._prompt.text,
            user=user,
            max_tokens=self._role.max_tokens,
            effort=self._role.effort,
            timeout_s=self._role.timeout_s,
            payload=SummaryPayload(status=record.status, language=language),
        )

    def _summary(
        self,
        record: CandidateRecord,
        language: Language,
        facts: list[SummaryFact],
        narrative: NarrativeOutput | None,
    ) -> Summary:
        words = self._catalog.summary_labels(language)
        return Summary(
            language=language,
            candidate_language=record.language,
            status=record.status,
            facts=facts,
            narrative=narrative,
            generated_by="llm" if narrative else "template",
            prompt_id=self._prompt.id if narrative else None,
            model=self._role.model if narrative else None,
            text=render_markdown(facts, narrative, words),
        )


def render_markdown(
    facts: list[SummaryFact], narrative: NarrativeOutput | None, words: SummaryLabels
) -> str:
    lines = [f"**{fact.label}:** {fact.value}" for fact in facts]
    if narrative is not None:
        sentiment = words.sentiments[narrative.sentiment]
        lines += [
            "",
            f"**{words.facts['overview']}:** {narrative.overview}",
            f"**{words.facts['sentiment']}:** {sentiment}. {narrative.sentiment_reason}",
        ]
        if narrative.observations:
            lines.append(f"**{words.facts['observations']}:**")
            lines += [f"- {note}" for note in narrative.observations]
    return "\n".join(lines)
