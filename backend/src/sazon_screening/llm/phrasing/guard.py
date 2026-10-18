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
    pending_question = "pending_question"  # a follow-up must end with the pending ask (008)


# A currency sign or name, or an amount per hour: what an invented pay promise looks like.
_PAY = re.compile(
    r"[€$£]|\b(?:eur|euros?|mxn|pesos?|usd|d[oó]lar(?:es)?|dollars?)\b"
    r"|\d+\s*(?:/\s*h(?:ora|our)?\b|(?:por|la|per|an)\s+hora?\b|(?:per|an)\s+hour\b)",
    re.IGNORECASE,
)
# Saying hello or introducing herself again after the greeting: "¡Hola! Soy Sofi..." on
# turn two, or reading the shift answer "tardes" as "¡Buenas tardes!". Opening words only,
# so "tardes anotadas" or "buenas noticias" pass; "soy Sofi" anywhere. Catalan "Hi ha..."
# ("there is") is not the English "Hi".
_GREETING = re.compile(
    r"^\W*(?:hola|hello|hi(?!\s+ha\b)|hey|buen[oa]s\s+(?:d[ií]as|tardes|noches)|buenas(?=\s*[!,.]|$)"
    r"|good\s+(?:morning|afternoon|evening)"
    r"|bon\s+dia|bona\s+(?:tarda|nit)|bones(?=\s*[!,.]|$))\b"  # Catalan (spec 017)
    r"|\b(?:soy|i\'?m|i\s+am)\s+sofi\b|(?<!\w)sóc\s+(?:la\s+)?sofi\b",
    re.IGNORECASE,
)
# Sofi is female: in Spanish she is "encantada", never "encantado" (eval 2026-10-12);
# in Catalan "encantada", never "encantat" (spec 017).
# Only words that can only be about herself in her own message.
_MASCULINE_SELF = re.compile(
    r"\b(?:encantado|(?:estoy|quedo)\s+(?:contento|seguro|encantado|agradecido))\b"
    r"|\b(?:encantat|(?:estic|em\s+quedo)\s+(?:content|segur|encantat|agraït))(?!\w)",
    re.IGNORECASE,
)
_GENDERED = (Language.es, Language.ca)  # Sofi's own words show her gender
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿⭐⭕]")
_MAX_EMOJI = 1


def check(
    text: str,
    action: EngineAction,
    ctx: RenderContext,
    caps: LengthCaps,
    *,
    language_check: bool = True,
    reference: str = "",
) -> list[Violation]:
    """All rules the reply breaks; an empty list means it can be sent."""
    if not text.strip():
        return [Violation.empty]
    found: list[Violation] = []
    if len(text) > length_cap(action, caps, faq_answer=ctx.faq_answer):
        found.append(Violation.too_long)
    if text.count("?") != (1 if expects_question(action) else 0):
        found.append(Violation.question_count)
    if _invented_pay(text, " ".join((ctx.faq_answer or "", *ctx.faq_approved)), reference):
        found.append(Violation.pay_or_currency)
    emoji = len(_EMOJI.findall(text))
    if emoji > _MAX_EMOJI or (emoji and action.primary.type in NO_EMOJI):
        found.append(Violation.emoji)
    if not ctx.is_greeting and _GREETING.search(text):
        found.append(Violation.repeated_greeting)
    if action.language in _GENDERED and _MASCULINE_SELF.search(text):
        found.append(Violation.masculine_form)
    if _name_overused(text, ctx, reference):
        found.append(Violation.name_overused)
    if language_check and dominant_language(text) not in (None, action.language):
        found.append(Violation.wrong_language)
    return found


def check_follow_up(
    text: str,
    *,
    question: str,
    reference: str,
    language: Language,
    ctx: RenderContext,
    caps: LengthCaps,
    language_check: bool = True,
) -> list[Violation]:
    """Spec 008 FR-3: a reminder is short, ends with the pending question word for word
    (so the candidate knows exactly what to answer) and follows the usual rules."""
    if not text.strip():
        return [Violation.empty]
    found: list[Violation] = []
    if len(text) > caps.default:
        found.append(Violation.too_long)
    if not _squash(text).endswith(_squash(question)):
        found.append(Violation.pending_question)
    if _invented_pay(text, "", reference):
        found.append(Violation.pay_or_currency)
    if len(_EMOJI.findall(text)) > _MAX_EMOJI:
        found.append(Violation.emoji)
    if _GREETING.search(text):
        found.append(Violation.repeated_greeting)
    if language in _GENDERED and _MASCULINE_SELF.search(text):
        found.append(Violation.masculine_form)
    if _name_overused(text, ctx, reference):
        found.append(Violation.name_overused)
    if language_check and dominant_language(text) not in (None, language):
        found.append(Violation.wrong_language)
    return found


def _squash(text: str) -> str:
    return " ".join(text.split())


def _name_overused(text: str, ctx: RenderContext, reference: str) -> bool:
    """The name rests after each use; names the reference itself contains (the recap's
    "Nombre completo" line) do not count."""
    if not ctx.first_name or ctx.name_to_use is not None:
        return False
    return mentions(text, ctx.first_name) > mentions(reference, ctx.first_name)


def _invented_pay(text: str, approved: str, reference: str = "") -> bool:
    """Money talk is allowed only when it comes word for word from an approved FAQ answer.

    The currency alone is not enough: "15 €" when the approved answer says "9 y 12 €"
    is a promise nobody made (009 AC-5). So once a reply talks money, every number in
    it must also be in the approved answer (or in the reference message, e.g. a time).
    """
    approved = approved.lower()
    money = list(_PAY.finditer(text))
    if any(match.group(0).lower() not in approved for match in money):
        return True
    if not money:
        return False
    allowed = set(_NUMBER.findall(approved)) | set(_NUMBER.findall(reference))
    return any(number not in allowed for number in _NUMBER.findall(text))
