"""T6: our own retry loop under a per-turn deadline (FR-23, NFR-1, AC-26)."""

from collections.abc import Awaitable, Callable

import pytest

from sazon_screening.llm.client.base import FailureKind, LLMResult, Usage
from sazon_screening.llm.client.retry import Deadline, RetryPolicy, call_with_retry
from tests.llm.support import FakeClock

POLICY = RetryPolicy(max_attempts=3, backoff_s=0.5, min_call_s=1.0)

Call = Callable[[float], Awaitable[LLMResult[str]]]


class ScriptedCall:
    """Returns queued results; a timeout eats the whole per-attempt timeout on the clock."""

    def __init__(self, clock: FakeClock, *results: LLMResult[str]) -> None:
        self.clock = clock
        self.results = list(results)
        self.timeouts: list[float] = []

    async def __call__(self, timeout_s: float) -> LLMResult[str]:
        self.timeouts.append(timeout_s)
        result = self.results.pop(0)
        if result.failure is FailureKind.timeout:
            self.clock.advance(timeout_s)
        else:
            self.clock.advance(result.latency_ms / 1000)
        return result


def ok(text: str = "hola") -> LLMResult[str]:
    return LLMResult(value=text, latency_ms=200, usage=Usage(input_tokens=10, output_tokens=5))


def failed(kind: FailureKind) -> LLMResult[str]:
    return LLMResult(failure=kind, latency_ms=100, usage=Usage(input_tokens=10))


async def run(
    call: Call, clock: FakeClock, *, budget_s: float = 15, role_timeout_s: float = 6
) -> LLMResult[str]:
    return await call_with_retry(
        call,
        role_timeout_s=role_timeout_s,
        deadline=Deadline(clock, budget_s),
        policy=POLICY,
        sleep=clock.sleep,
    )


@pytest.mark.anyio
@pytest.mark.ac("003:AC-26")
async def test_timeout_then_success_is_ok_with_two_attempts() -> None:
    clock = FakeClock()
    call = ScriptedCall(clock, failed(FailureKind.timeout), ok())
    result = await run(call, clock)
    assert result.ok
    assert result.value == "hola"
    assert result.attempts == 2  # retries = 1
    assert result.usage == Usage(input_tokens=20, output_tokens=5)  # summed over attempts


@pytest.mark.anyio
@pytest.mark.parametrize("kind", [FailureKind.refusal, FailureKind.client_error])
async def test_non_retryable_failure_is_tried_once(kind: FailureKind) -> None:
    clock = FakeClock()
    call = ScriptedCall(clock, failed(kind))
    result = await run(call, clock)
    assert (result.failure, result.attempts, len(call.timeouts)) == (kind, 1, 1)


@pytest.mark.anyio
async def test_attempt_timeout_is_capped_by_the_time_left() -> None:
    clock = FakeClock()
    call = ScriptedCall(clock, ok())
    await run(call, clock, budget_s=4, role_timeout_s=6)
    assert call.timeouts == [4]


@pytest.mark.anyio
async def test_too_little_time_left_skips_the_call() -> None:
    clock = FakeClock()
    call = ScriptedCall(clock)
    result = await run(call, clock, budget_s=0.5)
    assert result.failure is FailureKind.budget_exhausted
    assert result.attempts == 0
    assert call.timeouts == []


@pytest.mark.anyio
@pytest.mark.ac("003:AC-26")
async def test_repeated_timeouts_stop_before_the_deadline() -> None:
    clock = FakeClock()
    call = ScriptedCall(clock, *(failed(FailureKind.timeout) for _ in range(3)))
    result = await run(call, clock, budget_s=10, role_timeout_s=6)
    assert result.failure is FailureKind.timeout
    assert call.timeouts == [6, 3.5]  # second attempt gets what is left after backoff
    assert clock.now <= 10


@pytest.mark.anyio
async def test_backoff_grows_and_goes_through_the_injected_sleep() -> None:
    clock = FakeClock()
    call = ScriptedCall(
        clock, failed(FailureKind.server_error), failed(FailureKind.rate_limited), ok()
    )
    result = await run(call, clock)
    assert result.ok
    assert result.attempts == 3
    assert clock.sleeps == [0.5, 1.0]  # backoff_s x attempt


def test_deadline_never_goes_negative() -> None:
    clock = FakeClock()
    deadline = Deadline(clock, 2)
    clock.advance(5)
    assert deadline.remaining() == 0
