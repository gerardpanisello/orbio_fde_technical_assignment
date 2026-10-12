"""Render an engine action with the catalog templates (FR-16, ADR 0006).

Templates are the fallback whenever the model fails or breaks a rule, the phrasing in
fake mode, and the `<reference_message>` the model rewrites. So they must always say
exactly what the action says, in the action's register: prefaces first (in the
engine's order), then the primary action, as one message.
"""

import re
from collections.abc import Mapping
from datetime import date

from pydantic import BaseModel, ConfigDict

from sazon_screening.config import EngineConfig
from sazon_screening.engine import (
    AckCorrection,
    AnswerFaq,
    AskField,
    CloseDisqualified,
    CloseWaitlisted,
    ConfirmAmbiguous,
    ConfirmInterview,
    ConfirmValue,
    EngineAction,
    OfferSlots,
    Preface,
    PrimaryAction,
    ReaskField,
    Redirect,
    ShowRecap,
)
from sazon_screening.llm.phrasing.catalog import MessageCatalog, RegisterCatalog
from sazon_screening.llm.phrasing.labels import area_label, field_values, option_label, slot_label
from sazon_screening.llm.slots import SlotDisplay
from sazon_screening.vocab import FieldName, Language


class RenderContext(BaseModel):
    """What phrasing needs beyond the action itself."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    privacy_url: str
    first_name: str | None = None
    last_candidate_message: str | None = None
    faq_answer: str | None = None  # FR-17 hook for 009: an approved answer text
    slots: dict[str, SlotDisplay] = {}
    is_greeting: bool = False  # start(): the consent ask is phrased as the greeting
    # Sofi's last messages, oldest first: the model varies its opener against them, and
    # the name rests for NAME_REST messages after each use (eval 2026-10-12).
    recent_agent_messages: tuple[str, ...] = ()
    today: date | None = None  # the recap says "mañana" for tomorrow's date

    @property
    def name_to_use(self) -> str | None:
        """The first name, unless one of Sofi's last NAME_REST messages already used it."""
        if not self.first_name:
            return None
        recent = self.recent_agent_messages[-NAME_REST:]
        return None if any(mentions(text, self.first_name) for text in recent) else self.first_name


NAME_REST = 3  # at most one message in four uses the candidate's name


def mentions(text: str, name: str) -> int:
    """How often `name` appears as a whole word: in "¡Gracias, Ana!", not in "semana"."""
    return len(re.findall(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE))


def render_template(
    action: EngineAction, ctx: RenderContext, catalog: MessageCatalog, config: EngineConfig
) -> str:
    """The full message for `action`. `no_message` renders as an empty string."""
    entry = catalog.for_register(action.register)
    parts = [_preface(p, ctx, entry) for p in action.prefaces]
    parts.append(_primary(action.primary, ctx, entry, config, action.language))
    return " ".join(part for part in parts if part)


def _preface(preface: Preface, ctx: RenderContext, entry: RegisterCatalog) -> str:
    texts = entry.templates.prefaces
    match preface:
        case Redirect(reason="abuse"):
            return texts.redirect_abuse
        case Redirect():
            return texts.redirect_off_topic
        case AckCorrection(fields=fields):
            names = ", ".join(entry.labels.fields[name] for name in fields)
            return texts.ack_correction.format(fields=names)
        case AnswerFaq():
            return ctx.faq_answer or texts.faq_holding  # never an answer from model knowledge
    return ""


def _primary(
    primary: PrimaryAction,
    ctx: RenderContext,
    entry: RegisterCatalog,
    config: EngineConfig,
    language: Language,
) -> str:
    templates = entry.templates
    match primary:
        case AskField(field=FieldName.consent) if ctx.is_greeting:
            return templates.greeting.format(privacy_url=ctx.privacy_url)
        case AskField(field=field):
            return templates.ask_field[field]
        case ReaskField(field=field, reason=reason, options=options):
            labels = [
                option_label(
                    field,
                    option,
                    config=config,
                    language=language,
                    labels=entry.labels,
                    slots=ctx.slots,
                )
                for option in options
            ]
            suffix = f" ({', '.join(labels)})" if labels else ""
            return templates.reask_field[reason].format(
                field=entry.labels.fields[field], options=suffix
            )
        case ConfirmAmbiguous(options=options):
            names = [area_label(option.id, config, language) for option in options]
            return templates.confirm_ambiguous.format(options=_numbered(names))
        case ConfirmValue(value=value):
            return templates.confirm_value.format(years=value.years)
        case ShowRecap(profile=profile):
            values = field_values(profile, config, language, entry.labels, today=ctx.today)
            lines = [
                f"• {entry.labels.fields[name].capitalize()}: {v}" for name, v in values.items()
            ]
            return templates.show_recap.format(recap="\n".join(lines))
        case OfferSlots(slot_ids=slot_ids):
            names = [slot_label(slot_id, ctx.slots, language) for slot_id in slot_ids]
            return templates.offer_slots.format(slots=_numbered(names))
        case CloseDisqualified(reason=reason):
            return templates.close_disqualified[reason]
        case ConfirmInterview(slot_id=slot_id):
            return templates.confirm_interview.format(slot=slot_label(slot_id, ctx.slots, language))
        case CloseWaitlisted(area_id=area_id):
            return templates.close_waitlisted.format(zone=area_label(area_id, config, language))
    return _fixed_text(primary, entry)


def _fixed_text(primary: PrimaryAction, entry: RegisterCatalog) -> str:
    """Actions whose text has no placeholders: looked up by their type."""
    templates = entry.templates
    texts: Mapping[str, str] = {
        "ask_correction_field": templates.ask_correction_field,
        "close_needs_review": templates.close_needs_review,
        "close_opted_out": templates.close_opted_out,
        "close_qualified_unscheduled": templates.close_qualified_unscheduled,
        "handoff_to_human": templates.handoff_to_human,
        "closed_ack": templates.closed_ack,
    }
    return texts.get(primary.type, "")  # no_message: nothing to say


def _numbered(items: list[str]) -> str:
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))
