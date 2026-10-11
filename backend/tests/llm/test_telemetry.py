"""T8: one telemetry record per LLM call, with cost and no candidate text (FR-27, NFR-5)."""

import logging

import pytest

from sazon_screening.llm.client.base import (
    Effort,
    FailureKind,
    LLMRequest,
    LLMResult,
    Role,
    Usage,
)
from sazon_screening.llm.settings import ModelPrice
from sazon_screening.llm.telemetry import CallTelemetry, estimate_cost, log_call, telemetry_from

PRICE = ModelPrice(input=1.0, output=5.0, cache_read=0.1, cache_write=1.25)
PRICES = {"claude-haiku-5-5": PRICE}
CANDIDATE_TEXT = "Me llamo Ana López y vivo en Coyoacán"
SYSTEM_TEXT = "You extract fields from candidate messages"

# FR-27: what every call record must carry.
FR27_FIELDS = {
    "role",
    "model",
    "prompt_id",
    "prompt_sha",
    "latency_ms",
    "usage",
    "attempts",
    "stop_reason",
    "outcome",
    "failure",
    "error_class",
    "cost_usd",
}


def request() -> LLMRequest:
    return LLMRequest(
        role=Role.extraction,
        model="claude-haiku-5-5",
        prompt_id="extraction.v1",
        prompt_sha="0a1b2c3d",
        system=SYSTEM_TEXT,
        user=f"<candidate_message>{CANDIDATE_TEXT}</candidate_message>",
        max_tokens=100,
        effort=Effort.low,
        timeout_s=6,
    )


def test_cost_prices_each_token_kind_separately() -> None:
    usage = Usage(
        input_tokens=1_000, output_tokens=200, cache_read_tokens=10_000, cache_write_tokens=2_000
    )
    # (1000 x 1.0 + 200 x 5.0 + 10000 x 0.1 + 2000 x 1.25) / 1M = 5500 / 1M
    assert estimate_cost(usage, PRICE) == pytest.approx(0.0055)


def test_ok_call_has_every_fr27_field() -> None:
    result: LLMResult[str] = LLMResult(
        value="x", stop_reason="end_turn", usage=Usage(input_tokens=1_000), latency_ms=900
    )
    telemetry = telemetry_from(request(), result, PRICES)
    assert set(CallTelemetry.model_fields) == FR27_FIELDS
    assert telemetry.outcome == "ok"
    assert telemetry.cost_usd == pytest.approx(0.001)
    assert (telemetry.prompt_id, telemetry.prompt_sha) == ("extraction.v1", "0a1b2c3d")


def test_failed_call_records_the_failure() -> None:
    result: LLMResult[str] = LLMResult(
        failure=FailureKind.timeout, attempts=2, error_class="APITimeoutError"
    )
    telemetry = telemetry_from(request(), result, PRICES)
    assert (telemetry.outcome, telemetry.failure, telemetry.attempts) == (
        "failure",
        FailureKind.timeout,
        2,
    )
    assert telemetry.error_class == "APITimeoutError"


def test_unpriced_model_costs_nothing() -> None:
    fake_request = request().model_copy(update={"model": "fake-rules"})
    telemetry = telemetry_from(fake_request, LLMResult(value="x"), PRICES)
    assert telemetry.cost_usd == 0


@pytest.mark.ac("003:AC-24")
def test_log_record_carries_no_request_text(caplog: pytest.LogCaptureFixture) -> None:
    telemetry = telemetry_from(request(), LLMResult(value="x"), PRICES)
    with caplog.at_level(logging.INFO, logger="sazon_screening.llm"):
        log_call(telemetry, conversation_id="conv-42")
    [record] = caplog.records
    everything = f"{record.getMessage()} {vars(record)}"
    assert "conv-42" in everything
    assert "extraction.v1" in everything
    assert CANDIDATE_TEXT not in everything
    assert SYSTEM_TEXT not in everything
