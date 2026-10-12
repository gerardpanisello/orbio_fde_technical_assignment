"""Deterministic checks on every phrased reply before it is sent (FR-15, ADR 0006).

Cheap code checks, not a second model: length, one question when asking (none when
closing), no pay or currency the model made up, emoji limits, no second hello once the
greeting is sent and, conservatively, the language. Any violation means the template is
sent instead. Deeper guardrails are 007.
"""

import re
from enum import StrEnum

from sazon_screening.engine import EngineAction
from sazon_screening.llm.phrasing.language import dominant_language
from sazon_screening.llm.phrasing.policy import NO_EMOJI, expects_question, length_cap
from sazon_screening.llm.phrasing.templates import RenderContext, mentions
from sazon_screening.llm.settings import LengthCaps
from sazon_screening.vocab import Language


class Violation(StrEnum):
    empty = "empty"
    too_long = "too_long"
    question_count = "question_count"
    pay_or_currency = "pay_or_currency"
    emoji = "emoji"
    wrong_language = "wrong_language"
    repeated_greeting = "repeated_greeting"
    masculine_form = "masculine_form"
    name_overused = "name_overused"


# A currency sign or name, or an amount per hour: what an invented pay promise looks like.
_PAY = re.compile(
    r"[€$£]|\b(?:eur|euros?|mxn|pesos?|usd|d[oó]lar(?:es)?|dollars?)\b"
    r"|\d+\s*(?:/\s*h(?:ora|our)?\b|(?:por|la|per|an)\s+hora?\b|(?:per|an)\s+hour\b)",
    re.IGNORECASE,
)
# Saying hello or introducing herself again after the greeting: "¡Hola! Soy Sofi..." on
# turn two, or reading the shift answer "tardes" as "¡Buenas tardes!". Opening words only,
# so "tardes anotadas" or "buenas noticias" pass; "soy Sofi" anywhere.
_GREETING = re.compile(
    r"^\W*(?:hola|hello|hi|hey|buen[oa]s\s+(?:d[ií]as|tardes|noches)|buenas(?=\s*[!,.]|$)"
    r"|good\s+(?:morning|afternoon|evening))\b"
    r"|\b(?:soy|i\'?m|i\s+am)\s+sofi\b",
    re.IGNORECASE,
)
# Sofi is female: in Spanish she is "encantada", never "encantado" (eval 2026-10-12).
# Only words that can only be about herself in her own message.
_MASCULINE_SELF = re.compile(
    r"\b(?:encantado|(?:estoy|quedo)\s+(?:contento|seguro|encantado|agradecido))\b",
    re.IGNORECASE,
)
_EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿⭐⭕]")
_MAX_EMOJI = 1


def check(
    text: str,
    action: EngineAction,
    ctx: RenderContext,
    caps: LengthCaps,
    *,
    language_check: bool = True,
) -> list[Violation]:
    """All rules the reply breaks; an empty list means it can be sent."""
    if not text.strip():
        return [Violation.empty]
    found: list[Violation] = []
    if len(text) > length_cap(action, caps, faq_answer=ctx.faq_answer):
        found.append(Violation.too_long)
    if text.count("?") != (1 if expects_question(action) else 0):
        found.append(Violation.question_count)
    if _invented_pay(text, ctx.faq_answer):
        found.append(Violation.pay_or_currency)
    emoji = len(_EMOJI.findall(text))
    if emoji > _MAX_EMOJI or (emoji and action.primary.type in NO_EMOJI):
        found.append(Violation.emoji)
    if not ctx.is_greeting and _GREETING.search(text):
        found.append(Violation.repeated_greeting)
    if action.language is Language.es and _MASCULINE_SELF.search(text):
        found.append(Violation.masculine_form)
    if ctx.first_name and ctx.name_to_use is None and mentions(text, ctx.first_name):
        found.append(Violation.name_overused)  # the name rests after each use
    if language_check and dominant_language(text) not in (None, action.language):
        found.append(Violation.wrong_language)
    return found


def _invented_pay(text: str, faq_answer: str | None) -> bool:
    """Money talk is allowed only when it comes word for word from the approved FAQ answer."""
    approved = (faq_answer or "").lower()
    return any(match.group(0).lower() not in approved for match in _PAY.finditer(text))
