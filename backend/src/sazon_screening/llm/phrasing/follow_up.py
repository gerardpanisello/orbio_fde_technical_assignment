"""The reminder text when a candidate goes quiet (spec 008 FR-3), from the templates.

It picks up exactly where the conversation stopped: the pending question, rendered by
the same templates as the original ask, after a short progress sentence. The result is
the fallback, the fake's reply, the WhatsApp template text past the 24 h window, and the
reference the model rewrites. The engine is not involved: the state is only read.
"""

import re
import warnings
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sazon_screening.config import EngineConfig
from sazon_screening.engine import (
    FIELD_ORDER,
    ConversationState,
    EngineAction,
    pending_action,
    register_for,
)
from sazon_screening.llm.phrasing.catalog import FollowUps, MessageCatalog
from sazon_screening.llm.phrasing.templates import RenderContext, render_template
from sazon_screening.vocab import FieldName, FieldStatus, Language, PendingKind, Register

FollowUpKind = Literal["nudge", "last_call"]
_NOT_COUNTED = (FieldName.consent, FieldName.zone)  # consent is separate; zone goes with location
_SPACES = re.compile(r"[ \t]{2,}")


# `register` is the contract name (ADR 0005); see engine/actions.py for why the warning is safe.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message='Field name "register"', category=UserWarning)

    class FollowUpText(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        text: str  # the template reminder, within the length cap
        question: str  # the pending ask it ends with
        language: Language
        register: Register


def render_follow_up(
    state: ConversationState,
    kind: FollowUpKind,
    ctx: RenderContext,
    catalog: MessageCatalog,
    config: EngineConfig,
    *,
    max_chars: int,
) -> FollowUpText:
    """The reminder for the pending ask. Longest version that fits `max_chars`: with the
    progress sentence, then without it, then the bare question."""
    location = state.profile.location.value
    register = register_for(
        state.language,
        location.country if location else None,
        state.country_hint,
        default_country=config.screening.default_country,
    )
    templates = catalog.for_register(register).templates
    texts = templates.follow_up
    question = pending_question(state, register, ctx, catalog, config)
    progress = progress_sentence(texts, remaining_questions(state))
    template = texts.last_call if kind == "last_call" else texts.nudge
    candidates = [
        _tidy(template.format(progress=progress, question=question)),
        _tidy(template.format(progress="", question=question)),
        question,
    ]
    text = next((c for c in candidates if len(c) <= max_chars), question)
    return FollowUpText(text=text, question=question, language=state.language, register=register)


def pending_question(
    state: ConversationState,
    register: Register,
    ctx: RenderContext,
    catalog: MessageCatalog,
    config: EngineConfig,
) -> str:
    """What Sofi is waiting for, as the same template that asked it. The recap and the
    slot list are too long for a reminder: a short question stands in for them."""
    templates = catalog.for_register(register).templates
    if state.pending.kind is PendingKind.recap:
        return templates.follow_up.recap_question
    if state.pending.kind is PendingKind.slot:
        return templates.ask_field[FieldName.slot]
    action = EngineAction(
        primary=pending_action(state), prefaces=[], language=state.language, register=register
    )
    plain = ctx.model_copy(update={"is_greeting": False, "faq_answer": None, "faq_approved": ()})
    return render_template(action, plain, catalog, config)


def remaining_questions(state: ConversationState) -> int:
    """Questions left, counting the pending one: for "Solo nos faltan 3 preguntas"."""
    if state.pending.kind in (PendingKind.recap, PendingKind.slot, PendingKind.correction_field):
        return 0
    profile = state.profile
    count = 0 if state.consent is True else 1
    for field in FIELD_ORDER:
        if field not in _NOT_COUNTED:
            count += getattr(profile, field.value).status is FieldStatus.not_asked
    return max(count, 1)  # something is pending


def progress_sentence(texts: FollowUps, remaining: int) -> str:
    if remaining <= 0:
        return texts.progress_done
    if remaining == 1:
        return texts.progress_one
    return texts.progress_many.format(remaining=remaining)


def _tidy(text: str) -> str:
    return _SPACES.sub(" ", text).strip()
