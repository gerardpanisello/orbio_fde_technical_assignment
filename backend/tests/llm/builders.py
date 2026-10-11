"""Short builders for LLM layer tests (plan §7.1)."""

from typing import Any

from sazon_screening.llm.extraction.pending import OptionView, PendingView
from sazon_screening.llm.extraction.schema import ExtractionOutput
from sazon_screening.vocab import FieldName, PendingKind


def out(**fields: Any) -> ExtractionOutput:
    """An extraction result with only the given fields set."""
    return ExtractionOutput(**fields)


def pending(
    kind: PendingKind = PendingKind.ask,
    field: FieldName | None = None,
    options: tuple[str, ...] = (),
) -> PendingView:
    """A pending ask; option labels are just their ids."""
    return PendingView(
        kind=kind,
        field=field,
        options=[OptionView(id=option, label=option) for option in options],
        current_values={},
    )


def asking(field: FieldName) -> PendingView:
    return pending(PendingKind.ask, field)
