"""The extraction stage: candidate message -> engine input (FR-5, FR-9, FR-10, NFR-4).

Read top to bottom: preprocess (no LLM call for media or blank messages), build the
request, call the model with retries under the turn deadline, map the result. Every
failure, including a bug in our own mapping, becomes an `extraction_failed` turn: the
engine then asks the same question again without using up a re-ask (FR-27 of 002).
Nothing in here raises for an LLM problem (FR-4).
"""

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Literal

import anyio
from pydantic import BaseModel, ConfigDict

from sazon_screening.engine import CandidateTurn, Signals, TurnContext
from sazon_screening.llm.client.base import FailureKind, LLMClient, LLMRequest, LLMResult, Role
from sazon_screening.llm.client.retry import Deadline, call_with_retry
from sazon_screening.llm.extraction.mapping import DroppedProposal, Mapped, to_turn_input
from sazon_screening.llm.extraction.pending import PendingView
from sazon_screening.llm.extraction.schema import ExtractionOutput, Sentiment
from sazon_screening.llm.prompts import PromptRegistry
from sazon_screening.llm.settings import LLMConfig
from sazon_screening.llm.telemetry import CallTelemetry, log_call, telemetry_from
from sazon_screening.vocab import Language

logger = logging.getLogger("sazon_screening.llm")


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InboundMessage(_Frozen):
    text: str
    kind: Literal["text", "media"] = "text"  # media: the channel says it is not text


class TranscriptEntry(_Frozen):
    role: Literal["candidate", "agent"]
    text: str


class Skipped(_Frozen):
    """Nothing to extract and nothing for the engine: the pipeline answers by template."""

    reason: Literal["media"]


class ExtractionTrace(_Frozen):
    outcome: Literal["ok", "failed", "skipped"]
    failure: FailureKind | None = None
    skipped_reason: Literal["empty", "media", "event"] | None = None
    truncated: bool = False
    dropped: list[DroppedProposal] = []
    faq_question: str | None = None
    sentiment: Sentiment | None = None


ExtractionResult = tuple[Mapped | Skipped, ExtractionTrace, list[CallTelemetry]]


class Extractor:
    def __init__(
        self,
        *,
        client: LLMClient,
        config: LLMConfig,
        prompts: PromptRegistry,
        sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
    ) -> None:
        self._client = client
        self._config = config
        self._role = config.roles[Role.extraction]
        self._prompt = prompts.load(self._role.prompt)
        self._sleep = sleep

    async def extract(
        self,
        message: InboundMessage,
        history: Sequence[TranscriptEntry],
        pending: PendingView,
        state_language: Language,
        context: TurnContext,
        deadline: Deadline,
        *,
        conversation_id: str | None = None,
    ) -> ExtractionResult:
        if self._is_media(message):
            return (
                Skipped(reason="media"),
                ExtractionTrace(outcome="skipped", skipped_reason="media"),
                [],
            )
        if not message.text.strip():  # the engine counts an empty answer as unclear
            empty = Mapped(turn_input=CandidateTurn(context=context))
            return empty, ExtractionTrace(outcome="skipped", skipped_reason="empty"), []
        text = message.text[: self._config.max_message_chars]
        truncated = len(text) < len(message.text)
        request = self._request(text, history, pending, state_language)
        result = await self._call(request, deadline)
        telemetry = telemetry_from(request, result, self._config.prices)
        log_call(telemetry, conversation_id=conversation_id)
        if result.value is None or result.failure is not None:
            return _failed(context, result.failure or FailureKind.empty, truncated, telemetry)
        try:
            mapped = to_turn_input(result.value, pending, context)
        except Exception as error:  # a bug in our mapping must not crash the conversation
            logger.exception(
                "extraction mapping failed: %s",
                type(error).__name__,
                extra={"conversation_id": conversation_id},
            )
            return _failed(context, FailureKind.unexpected, truncated, telemetry)
        trace = ExtractionTrace(
            outcome="ok",
            truncated=truncated,
            dropped=mapped.dropped,
            faq_question=mapped.faq_question,
            sentiment=mapped.sentiment,
        )
        return mapped, trace, [telemetry]

    # --- steps ---------------------------------------------------------------------------

    def _is_media(self, message: InboundMessage) -> bool:
        """A voice note or photo: the channel flags it, or sends a known placeholder text."""
        placeholders = {p.casefold() for p in self._config.media_placeholders}
        return message.kind == "media" or message.text.strip().casefold() in placeholders

    def _request(
        self,
        text: str,
        history: Sequence[TranscriptEntry],
        pending: PendingView,
        language: Language,
    ) -> LLMRequest:
        return LLMRequest(
            role=Role.extraction,
            model=self._role.model,
            prompt_id=self._prompt.id,
            prompt_sha=self._prompt.sha,
            system=self._prompt.text,  # static: the same bytes for every conversation
            user=self._user_content(text, history, pending, language),
            max_tokens=self._role.max_tokens,
            effort=self._role.effort,
            timeout_s=self._role.timeout_s,
        )

    def _user_content(
        self,
        text: str,
        history: Sequence[TranscriptEntry],
        pending: PendingView,
        language: Language,
    ) -> str:
        """All per-request data, candidate text delimited as data (NFR-4, plan §3.6)."""
        size = self._config.history_messages
        window = list(history)[-size:] if size else []
        cap = self._config.max_message_chars
        recent = "\n".join(_tagged(entry.role, entry.text[:cap]) for entry in window)
        return (
            f"<pending_ask>{pending.model_dump_json()}</pending_ask>\n"
            f"<conversation_language>{language.value}</conversation_language>\n"
            f"<recent_messages>\n{recent}\n</recent_messages>\n"
            f"{_tagged('candidate_message', text)}"
        )

    async def _call(self, request: LLMRequest, deadline: Deadline) -> LLMResult[ExtractionOutput]:
        async def attempt(timeout_s: float) -> LLMResult[ExtractionOutput]:
            timed = request.model_copy(update={"timeout_s": timeout_s})
            return await self._client.parse(timed, ExtractionOutput)

        return await call_with_retry(
            attempt,
            role_timeout_s=self._role.timeout_s,
            deadline=deadline,
            policy=self._config.retry,
            sleep=self._sleep,
        )


def _tagged(tag: str, text: str) -> str:
    """Wrap conversation text in a tag, neutralising `<` inside it.

    A candidate typing `</candidate_message>` must not be able to close the data block
    and write something that looks like our own instructions.
    """
    safe = text.replace("<", "\N{SINGLE LEFT-POINTING ANGLE QUOTATION MARK}")
    return f"<{tag}>{safe}</{tag}>"


def _failed(
    context: TurnContext, failure: FailureKind, truncated: bool, telemetry: CallTelemetry
) -> ExtractionResult:
    turn = CandidateTurn(signals=Signals(extraction_failed=True), context=context)
    trace = ExtractionTrace(outcome="failed", failure=failure, truncated=truncated)
    return Mapped(turn_input=turn), trace, [telemetry]
