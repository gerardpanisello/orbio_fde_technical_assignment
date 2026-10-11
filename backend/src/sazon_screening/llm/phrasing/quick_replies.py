"""Quick-reply buttons, built from the action alone (FR-14, plan §3.7).

Never from the model: a button's id goes straight back into extraction, so it must be
an id the engine offered. The same function serves the LLM and the template path, so
the buttons never depend on which one wrote the text (AC-13).
"""

from pydantic import BaseModel, ConfigDict

from sazon_screening.config import EngineConfig
from sazon_screening.engine import (
    AskField,
    ConfirmAmbiguous,
    ConfirmValue,
    EngineAction,
    OfferSlots,
    ReaskField,
    ShowRecap,
)
from sazon_screening.llm.phrasing.catalog import Labels, MessageCatalog
from sazon_screening.llm.phrasing.labels import ENUM_GROUPS, area_label, option_label, slot_label
from sazon_screening.llm.phrasing.templates import RenderContext
from sazon_screening.vocab import FieldName


class QuickReply(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str


def quick_replies_for(
    action: EngineAction, ctx: RenderContext, catalog: MessageCatalog, config: EngineConfig
) -> list[QuickReply]:
    labels = catalog.for_register(action.register).labels
    language = action.language
    match action.primary:
        case AskField(field=field):
            return _enum_replies(field, labels)
        case ReaskField(field=field, options=options) if options:
            return [
                QuickReply(
                    id=option,
                    label=option_label(
                        field,
                        option,
                        config=config,
                        language=language,
                        labels=labels,
                        slots=ctx.slots,
                    ),
                )
                for option in options
            ]
        case ReaskField(field=field):
            return _enum_replies(field, labels)
        case ConfirmValue() | ShowRecap():
            return _yes_no(labels)
        case ConfirmAmbiguous(options=options):
            return [QuickReply(id=o.id, label=area_label(o.id, config, language)) for o in options]
        case OfferSlots(slot_ids=slot_ids):
            return [QuickReply(id=s, label=slot_label(s, ctx.slots, language)) for s in slot_ids]
    return []  # free text, closes and acknowledgements


def _enum_replies(field: FieldName, labels: Labels) -> list[QuickReply]:
    if field not in ENUM_GROUPS:
        return []
    return [QuickReply(id=k, label=v) for k, v in labels.group(ENUM_GROUPS[field]).items()]


def _yes_no(labels: Labels) -> list[QuickReply]:
    return [QuickReply(id=k, label=v) for k, v in labels.yes_no.items()]
