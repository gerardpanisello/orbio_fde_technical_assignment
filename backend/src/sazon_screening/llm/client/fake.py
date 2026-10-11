"""Fake LLM client for tests and the offline demo (FR-24, plan §3.4).

Scripted mode returns queued outcomes, including every failure kind, so the real
mapping, guard, retry and fallback code runs in tests exactly as it would against the
API. It records every request, so tests can check what would have been sent (AC-9,
AC-25). Rules mode (the offline demo) arrives in T25.
"""

from collections import defaultdict
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from sazon_screening.llm.client.base import FailureKind, LLMRequest, LLMResult, Role, Usage


class ManualClock(Protocol):
    """A clock the fake can move forward, so latency and timeouts show on a test's clock."""

    def monotonic(self) -> float: ...

    def advance(self, seconds: float) -> None: ...


class Scripted(BaseModel):
    """One canned outcome for one call."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    value: Any = None  # a schema instance or dict (parse), or a str (text)
    raw_json: str | None = None  # validated like the SDK would: bad JSON / bad shape fail
    failure: FailureKind | None = None
    stop_reason: str | None = "end_turn"
    usage: Usage = Usage(input_tokens=100, output_tokens=20)
    latency_s: float = 0.05


class FakeLLMClient:
    def __init__(
        self,
        *,
        mode: Literal["rules", "scripted"],
        clock: ManualClock | None = None,
        script: dict[Role, list[Scripted]] | None = None,
    ) -> None:
        if mode == "rules":
            raise NotImplementedError("rules mode arrives in T25")
        self.name = f"fake-{mode}"
        self.calls: list[LLMRequest] = []
        self._clock = clock
        self._queues: defaultdict[Role, list[Scripted]] = defaultdict(list)
        for role, outcomes in (script or {}).items():
            self.push(role, *outcomes)

    def push(self, role: Role, *outcomes: Scripted) -> None:
        self._queues[role].extend(outcomes)

    def pending(self, role: Role) -> int:
        return len(self._queues[role])

    async def parse[T: BaseModel](self, request: LLMRequest, schema: type[T]) -> LLMResult[T]:
        outcome = self._next(request)
        if outcome.failure is not None or (outcome.value is None and outcome.raw_json is None):
            return self._failed(request, outcome)
        try:
            if outcome.raw_json is not None:
                value = schema.model_validate_json(outcome.raw_json)
            else:
                value = schema.model_validate(outcome.value)
        except ValidationError as error:
            bad_json = any(e["type"] == "json_invalid" for e in error.errors())
            kind = FailureKind.malformed if bad_json else FailureKind.schema_invalid
            return self._failed(request, outcome.model_copy(update={"failure": kind}))
        return self._result(request, outcome, value)

    async def text(self, request: LLMRequest) -> LLMResult[str]:
        outcome = self._next(request)
        if outcome.failure is not None or outcome.value is None:
            return self._failed(request, outcome)
        assert isinstance(outcome.value, str), "scripted text outcomes need a str value"
        return self._result(request, outcome, outcome.value)

    # --- internals ---------------------------------------------------------------------

    def _next(self, request: LLMRequest) -> Scripted:
        """Record the request and pop its outcome. An empty queue is a bug in the test."""
        self.calls.append(request)
        queue = self._queues[request.role]
        assert queue, f"nothing scripted for {request.role}"
        return queue.pop(0)

    def _latency_s(self, request: LLMRequest, outcome: Scripted) -> float:
        """A timeout costs the full request timeout, as it would against the real API."""
        seconds = request.timeout_s if outcome.failure is FailureKind.timeout else outcome.latency_s
        if self._clock is not None:
            self._clock.advance(seconds)
        return seconds

    def _result[T](self, request: LLMRequest, outcome: Scripted, value: T) -> LLMResult[T]:
        return LLMResult(
            value=value,
            stop_reason=outcome.stop_reason,
            usage=outcome.usage,
            latency_ms=round(self._latency_s(request, outcome) * 1000),
        )

    def _failed[T](self, request: LLMRequest, outcome: Scripted) -> LLMResult[T]:
        return LLMResult(
            failure=outcome.failure or FailureKind.empty,
            stop_reason=outcome.stop_reason,
            usage=outcome.usage,
            latency_ms=round(self._latency_s(request, outcome) * 1000),
            error_class="FakeFailure",
        )
