"""Retries under a per-turn deadline (plan §3.2, ADR 0007).

Why not the SDK's retries: they are invisible to telemetry (AC-26 counts attempts) and
two retries at a 6 s timeout can blow the 15 s turn ceiling (NFR-1). Here every attempt
gets `min(role timeout, time left)`, and we stop retrying when the time runs out.
"""

import time
from collections.abc import Awaitable, Callable
from typing import Protocol

import anyio
from pydantic import BaseModel, ConfigDict, Field

from sazon_screening.llm.client.base import RETRYABLE, FailureKind, LLMResult, Usage


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_attempts: int = Field(2, ge=1)
    backoff_s: float = Field(0.5, ge=0)
    min_call_s: float = Field(1.0, gt=0)  # less time left than this: don't even try


class Clock(Protocol):
    def monotonic(self) -> float: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()


class Deadline:
    """The time left in one candidate turn. Tests pass a fake clock instead of sleeping."""

    def __init__(self, clock: Clock, budget_s: float) -> None:
        self._clock = clock
        self._ends_at = clock.monotonic() + budget_s

    def remaining(self) -> float:
        return max(0.0, self._ends_at - self._clock.monotonic())


async def call_with_retry[T](
    call: Callable[[float], Awaitable[LLMResult[T]]],
    *,
    role_timeout_s: float,
    deadline: Deadline,
    policy: RetryPolicy,
    sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
) -> LLMResult[T]:
    """Run `call(timeout_s)` until it succeeds, fails for good, or the deadline is near.

    Returns the last result with `attempts`, latency and usage summed over attempts.
    If there was no time for even one call: `budget_exhausted` with 0 attempts.
    """
    last: LLMResult[T] | None = None
    attempts, latency_ms, usage = 0, 0, Usage()
    while attempts < policy.max_attempts and deadline.remaining() >= policy.min_call_s:
        attempts += 1
        last = await call(min(role_timeout_s, deadline.remaining()))
        latency_ms += last.latency_ms
        usage = usage + last.usage
        if last.failure not in RETRYABLE:
            break  # success, or a failure that would only repeat
        backoff = policy.backoff_s * attempts
        if attempts >= policy.max_attempts or deadline.remaining() - backoff < policy.min_call_s:
            break
        await sleep(backoff)
    if last is None:
        return LLMResult(failure=FailureKind.budget_exhausted, attempts=0)
    return last.model_copy(update={"attempts": attempts, "latency_ms": latency_ms, "usage": usage})
