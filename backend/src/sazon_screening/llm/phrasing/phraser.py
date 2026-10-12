"""The phrasing stage: engine action -> the message the candidate reads (FR-11..17).

Read top to bottom: render the template first (it is the fallback and the model's
reference), ask the model to say the same thing more naturally, check its text with
the guard, and send the template on any failure or violation. Quick replies always
come from code. Nothing in here raises: a bug in rendering still sends an apology.
"""

import json
import logging
import warnings
from collections.abc import Awaitable, Callable
from typing import Literal

import anyio
from pydantic import BaseModel, ConfigDict

from sazon_screening.config import EngineConfig
from sazon_screening.engine import EngineAction
from sazon_screening.llm.client.base import FailureKind, LLMClient, LLMRequest, LLMResult, Role
from sazon_screening.llm.client.retry import Deadline, call_with_retry
from sazon_screening.llm.delimit import tagged
from sazon_screening.llm.phrasing.catalog import MessageCatalog
from sazon_screening.llm.phrasing.guard import check
from sazon_screening.llm.phrasing.quick_replies import QuickReply, quick_replies_for
from sazon_screening.llm.phrasing.templates import RenderContext, render_template
from sazon_screening.llm.prompts import PromptRegistry
from sazon_screening.llm.settings import LLMConfig
from sazon_screening.llm.telemetry import CallTelemetry, log_call, telemetry_from
from sazon_screening.vocab import Language, Register

logger = logging.getLogger("sazon_screening.llm")

# Only if rendering a template itself fails (a bug: the catalog is checked at startup).
LAST_RESORT = {
    Language.es: "Perdona, he tenido un problema técnico. Una persona del equipo te escribirá.",
    Language.en: "Sorry, I had a technical problem. Someone from the team will write to you.",
}


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# `register` is the contract name (ADR 0005); see engine/actions.py for why the warning is safe.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message='Field name "register"', category=UserWarning)

    class OutboundMessage(_Frozen):
        """What the channel sends: text plus buttons, in the action's language and register."""

        text: str
        quick_replies: list[QuickReply]
        language: Language
        register: Register


class PhrasingTrace(_Frozen):
    outcome: Literal["ok", "fallback", "skipped"]
    violations: list[str] = []
    failure: FailureKind | None = None
    template_key: str = ""
    # 009 FR-8: only on turns with approved FAQ entries. False: the model said none of
    # them answers the question, so the holding template was sent (outcome stays "ok").
    faq_relevant: bool | None = None


class FaqReply(_Frozen):
    """Phrasing output when approved FAQ entries are attached (009 FR-8).

    Why a flag in the phrasing call and not a separate relevance call: the phrasing
    model already reads the question and the entries, so one structured field costs no
    extra round trip, and structured output makes the decision mandatory and typed (a
    sentinel in free text could be forgotten or half-written). The decision comes
    first, so the model judges relevance before it writes. Code acts on the flag: on
    `false` the model's text is discarded and the holding template is sent.
    """

    answers_question: bool
    message: str


class PhrasingPayload(_Frozen):
    """Structured input for the rule-based fake (never sent): it simply returns the template."""

    reference_message: str
    faq: bool = False  # approved entries attached: the reply is a `FaqReply`


PhraseResult = tuple[OutboundMessage | None, PhrasingTrace, list[CallTelemetry]]


class Phraser:
    def __init__(
        self,
        *,
        client: LLMClient,
        config: LLMConfig,
        catalog: MessageCatalog,
        prompts: PromptRegistry,
        engine_config: EngineConfig,
        sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
    ) -> None:
        self._client = client
        self._config = config
        self._catalog = catalog
        self._engine_config = engine_config
        self._role = config.roles[Role.phrasing]
        self._prompt = prompts.load(self._role.prompt)
        self._sleep = sleep

    async def phrase(
        self,
        action: EngineAction,
        ctx: RenderContext,
        deadline: Deadline,
        *,
        conversation_id: str | None = None,
    ) -> PhraseResult:
        key = template_key(action)
        if action.primary.type == "no_message":
            return None, PhrasingTrace(outcome="skipped", template_key=key), []
        try:
            reference = render_template(action, ctx, self._catalog, self._engine_config)
            buttons = quick_replies_for(action, ctx, self._catalog, self._engine_config)
        except Exception as error:  # a bug; the catalog is validated at startup
            logger.exception(
                "template rendering failed: %s",
                type(error).__name__,
                extra={"conversation_id": conversation_id},
            )
            apology = self._message(LAST_RESORT[action.language], [], action)
            trace = PhrasingTrace(
                outcome="fallback", failure=FailureKind.unexpected, template_key=key
            )
            return apology, trace, []

        request = self._request(action, ctx, reference, buttons)
        grounded = bool(ctx.faq_answer)  # approved entries attached (009)
        result, telemetry = await self._call(request, deadline, grounded)
        log_call(telemetry, conversation_id=conversation_id)

        if result.value is None or result.failure is not None:
            trace = PhrasingTrace(outcome="fallback", failure=result.failure, template_key=key)
            return self._message(reference, buttons, action), trace, [telemetry]
        relevant: bool | None = None
        if isinstance(result.value, FaqReply):
            relevant = result.value.answers_question
            if not relevant:  # FR-8: nothing approved answers it -> hold, never answer
                holding = self._holding(action, ctx, conversation_id)
                trace = PhrasingTrace(outcome="ok", template_key=key, faq_relevant=False)
                return self._message(holding, buttons, action), trace, [telemetry]
            text = result.value.message.strip()
        else:
            text = result.value.strip()
        violations = check(
            text,
            action,
            ctx,
            self._config.length_caps,
            language_check=self._config.guard.language_check,
            reference=reference,
        )
        if violations:
            trace = PhrasingTrace(
                outcome="fallback", violations=violations, template_key=key, faq_relevant=relevant
            )
            return self._message(reference, buttons, action), trace, [telemetry]
        trace = PhrasingTrace(outcome="ok", template_key=key, faq_relevant=relevant)
        return self._message(text, buttons, action), trace, [telemetry]

    # --- steps ---------------------------------------------------------------------------

    async def _call(
        self, request: LLMRequest, deadline: Deadline, grounded: bool
    ) -> tuple[LLMResult[str] | LLMResult[FaqReply], CallTelemetry]:
        """Plain text, or a `FaqReply` when approved FAQ entries are attached (FR-8)."""

        def timed(timeout_s: float) -> LLMRequest:
            return request.model_copy(update={"timeout_s": timeout_s})

        if grounded:
            parsed = await call_with_retry(
                lambda timeout_s: self._client.parse(timed(timeout_s), FaqReply),
                role_timeout_s=self._role.timeout_s,
                deadline=deadline,
                policy=self._config.retry,
                sleep=self._sleep,
            )
            return parsed, telemetry_from(request, parsed, self._config.prices)
        text = await call_with_retry(
            lambda timeout_s: self._client.text(timed(timeout_s)),
            role_timeout_s=self._role.timeout_s,
            deadline=deadline,
            policy=self._config.retry,
            sleep=self._sleep,
        )
        return text, telemetry_from(request, text, self._config.prices)

    def _holding(
        self, action: EngineAction, ctx: RenderContext, conversation_id: str | None
    ) -> str:
        """The template without the FAQ: the holding phrase, then the pending question."""
        ungrounded = ctx.model_copy(update={"faq_answer": None, "faq_approved": ()})
        try:
            return render_template(action, ungrounded, self._catalog, self._engine_config)
        except Exception as error:  # a bug; the same template just rendered with the FAQ
            logger.exception(
                "holding template failed: %s",
                type(error).__name__,
                extra={"conversation_id": conversation_id},
            )
            return LAST_RESORT[action.language]

    def _request(
        self, action: EngineAction, ctx: RenderContext, reference: str, buttons: list[QuickReply]
    ) -> LLMRequest:
        """Static system prompt; everything about this turn goes in delimited user content."""
        instruction = {
            "action": action.model_dump(mode="json"),
            "quick_reply_labels": [button.label for button in buttons],
        }
        parts = [
            tagged("instruction", json.dumps(instruction, ensure_ascii=False)),
            tagged("reference_message", reference),
            tagged("candidate_first_name", ctx.name_to_use or ""),
            tagged("candidate_last_message", ctx.last_candidate_message or ""),
            _recent_messages(ctx.recent_agent_messages[-RECENT_SHOWN:]),
        ]
        if ctx.faq_answer:  # 009: approved entries only, best first, blank line apart
            approved = ctx.faq_approved or (ctx.faq_answer,)
            parts.append(tagged("faq_answer", "\n\n".join(approved)))
        return LLMRequest(
            role=Role.phrasing,
            model=self._role.model,
            prompt_id=self._prompt.id,
            prompt_sha=self._prompt.sha,
            system=self._prompt.text,
            user="\n".join(parts),
            max_tokens=self._role.max_tokens,
            effort=self._role.effort,
            timeout_s=self._role.timeout_s,
            payload=PhrasingPayload(reference_message=reference, faq=bool(ctx.faq_answer)),
        )

    @staticmethod
    def _message(text: str, buttons: list[QuickReply], action: EngineAction) -> OutboundMessage:
        return OutboundMessage(
            text=text, quick_replies=buttons, language=action.language, register=action.register
        )


RECENT_SHOWN = 2  # Sofi's last messages the model sees, to vary its opener


def _recent_messages(texts: tuple[str, ...]) -> str:
    inner = "\n".join(tagged("sofi", text) for text in texts)
    return f"<recent_sofi_messages>\n{inner}\n</recent_sofi_messages>"


def template_key(action: EngineAction) -> str:
    """Which template the action uses, e.g. `reask_field.unclear`, for the trace."""
    primary = action.primary
    detail = getattr(primary, "reason", None) or getattr(primary, "field", None)
    return f"{primary.type}.{detail}" if isinstance(detail, str) else primary.type
