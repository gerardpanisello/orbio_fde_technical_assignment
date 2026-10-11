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
from sazon_screening.llm.client.base import FailureKind, LLMClient, LLMRequest, Role
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


class PhrasingPayload(_Frozen):
    """Structured input for the rule-based fake (never sent): it simply returns the template."""

    reference_message: str


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
        result = await call_with_retry(
            lambda timeout_s: self._client.text(
                request.model_copy(update={"timeout_s": timeout_s})
            ),
            role_timeout_s=self._role.timeout_s,
            deadline=deadline,
            policy=self._config.retry,
            sleep=self._sleep,
        )
        telemetry = telemetry_from(request, result, self._config.prices)
        log_call(telemetry, conversation_id=conversation_id)

        if result.value is None or result.failure is not None:
            trace = PhrasingTrace(outcome="fallback", failure=result.failure, template_key=key)
            return self._message(reference, buttons, action), trace, [telemetry]
        text = result.value.strip()
        violations = check(
            text,
            action,
            ctx,
            self._config.length_caps,
            language_check=self._config.guard.language_check,
        )
        if violations:
            trace = PhrasingTrace(outcome="fallback", violations=violations, template_key=key)
            return self._message(reference, buttons, action), trace, [telemetry]
        trace = PhrasingTrace(outcome="ok", template_key=key)
        return self._message(text, buttons, action), trace, [telemetry]

    # --- steps ---------------------------------------------------------------------------

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
            tagged("candidate_first_name", ctx.first_name or ""),
            tagged("candidate_last_message", ctx.last_candidate_message or ""),
        ]
        if ctx.faq_answer:
            parts.append(tagged("faq_answer", ctx.faq_answer))
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
            payload=PhrasingPayload(reference_message=reference),
        )

    @staticmethod
    def _message(text: str, buttons: list[QuickReply], action: EngineAction) -> OutboundMessage:
        return OutboundMessage(
            text=text, quick_replies=buttons, language=action.language, register=action.register
        )


def template_key(action: EngineAction) -> str:
    """Which template the action uses, e.g. `reask_field.unclear`, for the trace."""
    primary = action.primary
    detail = getattr(primary, "reason", None) or getattr(primary, "field", None)
    return f"{primary.type}.{detail}" if isinstance(detail, str) else primary.type
