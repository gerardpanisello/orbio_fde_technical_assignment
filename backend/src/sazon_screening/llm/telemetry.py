"""One telemetry record per LLM call (FR-27), for analytics (011) and cost tracking (NFR-2).

Built from the request's metadata and the result, never from its text: candidate
messages are personal data and must not end up in logs or dashboards (NFR-5).
"""

import logging
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sazon_screening.llm.client.base import FailureKind, LLMRequest, LLMResult, Role, Usage
from sazon_screening.llm.settings import ModelPrice

logger = logging.getLogger("sazon_screening.llm")
_PER_MILLION = 1_000_000


class CallTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Role
    model: str
    prompt_id: str
    prompt_sha: str
    latency_ms: int
    usage: Usage
    attempts: int
    stop_reason: str | None
    outcome: Literal["ok", "failure"]  # the stage decides "fallback"; see the turn trace
    failure: FailureKind | None
    error_class: str | None
    cost_usd: float


def estimate_cost(usage: Usage, price: ModelPrice) -> float:
    """USD for one call. Cached tokens are billed apart from plain input tokens."""
    total = (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_tokens * price.cache_read
        + usage.cache_write_tokens * price.cache_write
    )
    return total / _PER_MILLION


def telemetry_from[T](
    request: LLMRequest, result: LLMResult[T], prices: Mapping[str, ModelPrice]
) -> CallTelemetry:
    """A model without a price (e.g. the fake) costs 0: config validation covers real ones."""
    price = prices.get(request.model)
    return CallTelemetry(
        role=request.role,
        model=request.model,
        prompt_id=request.prompt_id,
        prompt_sha=request.prompt_sha,
        latency_ms=result.latency_ms,
        usage=result.usage,
        attempts=result.attempts,
        stop_reason=result.stop_reason,
        outcome="ok" if result.ok else "failure",
        failure=result.failure,
        error_class=result.error_class,
        cost_usd=estimate_cost(result.usage, price) if price is not None else 0.0,
    )


def log_call(telemetry: CallTelemetry, *, conversation_id: str | None = None) -> None:
    """One structured log line per call; metadata only, so it is safe to ship anywhere."""
    level = logging.INFO if telemetry.outcome == "ok" else logging.WARNING
    logger.log(
        level,
        "llm call %s %s: %s",
        telemetry.role.value,
        telemetry.model,
        telemetry.failure.value if telemetry.failure else "ok",
        extra={
            "conversation_id": conversation_id,
            "llm_call": telemetry.model_dump(mode="json"),
        },
    )
