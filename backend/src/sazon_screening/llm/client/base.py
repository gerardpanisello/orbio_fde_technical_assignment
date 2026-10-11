"""Types shared by every LLM client (plan §3.1).

The contract that keeps the rest of the layer simple: `parse` and `text` never raise for
API or model problems. Every failure comes back as a `FailureKind`, so the callers
handle one value instead of a zoo of SDK exceptions (FR-4, FR-23).
"""

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    """Which job a call does. Each role has its own model, prompt and limits in llm.yaml."""

    extraction = "extraction"
    phrasing = "phrasing"
    summary = "summary"
    judge = "judge"


class Effort(StrEnum):
    """How hard the model thinks (`output_config.effort`). `low` keeps chat turns fast."""

    low = "low"
    medium = "medium"
    high = "high"


class FailureKind(StrEnum):
    timeout = "timeout"
    connection = "connection"
    rate_limited = "rate_limited"
    server_error = "server_error"
    client_error = "client_error"  # 4xx other than 408/409/429: retrying will not help
    refusal = "refusal"
    max_tokens = "max_tokens"  # truncated output: never parsed
    malformed = "malformed"  # no usable structured output
    schema_invalid = "schema_invalid"  # output does not fit the schema
    empty = "empty"
    budget_exhausted = "budget_exhausted"  # the turn deadline left no time to call
    unexpected = "unexpected"  # a bug in our own code, caught at the stage boundary


# Transient problems on the provider's side; everything else fails the same way twice.
RETRYABLE = frozenset(
    {
        FailureKind.timeout,
        FailureKind.connection,
        FailureKind.rate_limited,
        FailureKind.server_error,
    }
)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Usage(_Frozen):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        """Retries cost tokens too: usage is summed over attempts."""
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
        )


class LLMRequest(_Frozen):
    role: Role
    model: str
    prompt_id: str
    prompt_sha: str
    system: str  # static and byte-stable, so it can be cached (no dates, no per-request data)
    user: str  # per-request data; candidate text only appears here, delimited (NFR-4)
    max_tokens: int
    effort: Effort
    timeout_s: float
    # Structured input for the rule-based fake, so it need not re-parse `user`.
    # NEVER sent to the API, and kept out of dumps and logs.
    payload: BaseModel | None = Field(None, exclude=True, repr=False)


class LLMResult[T](_Frozen):
    value: T | None = None
    failure: FailureKind | None = None
    stop_reason: str | None = None
    usage: Usage = Usage()
    latency_ms: int = 0
    attempts: int = 1
    error_class: str | None = None  # e.g. "APITimeoutError"; never the message (may echo input)

    @property
    def ok(self) -> bool:
        return self.failure is None and self.value is not None


class LLMClient(Protocol):
    """Anthropic or fake. Everything above this interface is real code under test."""

    name: str  # "anthropic" | "fake-rules" | "fake-scripted"

    async def parse[T: BaseModel](self, request: LLMRequest, schema: type[T]) -> LLMResult[T]:
        """Structured output validated against `schema`."""
        ...

    async def text(self, request: LLMRequest) -> LLMResult[str]:
        """Plain text output."""
        ...
