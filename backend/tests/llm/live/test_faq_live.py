"""Spec 009 live check: the real model answers a pay question from the approved entry.

Skipped unless ANTHROPIC_API_KEY and LLM_MODE=anthropic are set (tests/conftest.py).
"""

from datetime import date

import pytest

from sazon_screening.llm.extraction.extractor import InboundMessage, TranscriptEntry
from sazon_screening.llm.pipeline import build_agent
from sazon_screening.llm.trace import TurnContextIn, TurnResult
from sazon_screening.vocab import Country

TODAY = date(2026, 10, 12)


async def chat(country: Country, messages: list[str]) -> list[TurnResult]:
    agent = build_agent()
    context = TurnContextIn(country_hint=country)
    result = await agent.start_conversation(context=context)
    history = [TranscriptEntry(role="agent", text=result.reply.text if result.reply else "")]
    results = [result]
    for text in messages:
        result = await agent.handle_message(
            result.state, InboundMessage(text=text), history, today=TODAY, context=context
        )
        history.append(TranscriptEntry(role="candidate", text=text))
        if result.reply:
            history.append(TranscriptEntry(role="agent", text=result.reply.text))
        results.append(result)
    return results


@pytest.mark.live
@pytest.mark.anyio
@pytest.mark.parametrize(
    ("country", "entry", "figures"),
    [(Country.ES, "pay-es", ("9", "12", "€")), (Country.MX, "pay-mx", ("70", "95", "MXN"))],
    ids=["ES", "MX"],
)
async def test_the_real_model_answers_pay_from_the_approved_entry(
    country: Country, entry: str, figures: tuple[str, ...]
) -> None:
    last = (await chat(country, ["sí", "Me llamo Ana López", "¿cuánto se paga?"]))[-1]
    assert last.trace.faq is not None
    assert last.trace.faq.entry_ids[:1] == [entry]
    assert last.reply is not None
    text = last.reply.text
    assert all(figure in text for figure in figures), text
    assert text.rstrip().endswith("?"), text  # the pending question is asked again
    assert len(text) <= 600
