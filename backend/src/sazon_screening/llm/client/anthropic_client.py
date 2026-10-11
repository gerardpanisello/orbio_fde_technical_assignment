"""The real client: Claude through the Anthropic SDK (ADR 0001, plan §3.3).

The ONLY module that imports `anthropic` (NFR-7). Its job is translation, kept in pure
functions that are tested without network:
- `build_kwargs`: our request -> SDK arguments (cacheable static system block, one user
  message, never an assistant prefill, effort from config);
- `interpret_*`: SDK response -> `LLMResult`, checking `stop_reason` BEFORE any content;
- `classify`: SDK exception -> `FailureKind`.
SDK retries are off (`max_retries=0`): ours respect the turn deadline (ADR 0007).
"""

import json
import time
from typing import Any

import anthropic
from pydantic import BaseModel, SecretStr, ValidationError

from sazon_screening.llm.client.base import FailureKind, LLMRequest, LLMResult, Usage

_BAD_STOPS = {"refusal": FailureKind.refusal, "max_tokens": FailureKind.max_tokens}


class AnthropicClient:
    name = "anthropic"

    def __init__(self, api_key: SecretStr | None = None, *, sdk: Any = None) -> None:
        """`sdk` lets tests pass a stand-in; production builds the async SDK client."""
        if sdk is None:
            key = api_key.get_secret_value() if api_key else None
            sdk = anthropic.AsyncAnthropic(api_key=key, max_retries=0)
        self._sdk = sdk

    async def parse[T: BaseModel](self, request: LLMRequest, schema: type[T]) -> LLMResult[T]:
        started = time.monotonic()
        try:
            response = await self._sdk.messages.parse(
                **build_kwargs(request), output_format=schema, timeout=request.timeout_s
            )
        except Exception as error:  # every SDK or parsing error becomes a FailureKind
            return _failed(error, started)
        return _timed(interpret_parsed(response, schema), started)

    async def text(self, request: LLMRequest) -> LLMResult[str]:
        started = time.monotonic()
        try:
            response = await self._sdk.messages.create(
                **build_kwargs(request), timeout=request.timeout_s
            )
        except Exception as error:
            return _failed(error, started)
        return _timed(interpret_text(response), started)


def build_kwargs(request: LLMRequest) -> dict[str, Any]:
    """The SDK arguments. History travels inside the single user message, as data."""
    return {
        "model": request.model,
        "max_tokens": request.max_tokens,
        "system": [
            {"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}
        ],
        "messages": [{"role": "user", "content": request.user}],
        "output_config": {"effort": request.effort.value},
    }


def interpret_parsed[T: BaseModel](response: Any, schema: type[T]) -> LLMResult[T]:
    if (stopped := _stopped(response)) is not None:
        return LLMResult(
            failure=stopped, stop_reason=response.stop_reason, usage=usage_of(response)
        )
    parsed = response.parsed_output
    failure = None
    if parsed is None:
        failure = FailureKind.malformed
    elif not isinstance(parsed, schema):
        failure = FailureKind.schema_invalid
    return LLMResult(
        value=None if failure else parsed,
        failure=failure,
        stop_reason=response.stop_reason,
        usage=usage_of(response),
    )


def interpret_text(response: Any) -> LLMResult[str]:
    if (stopped := _stopped(response)) is not None:
        return LLMResult(
            failure=stopped, stop_reason=response.stop_reason, usage=usage_of(response)
        )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return LLMResult(
        value=text or None,
        failure=None if text else FailureKind.empty,
        stop_reason=response.stop_reason,
        usage=usage_of(response),
    )


def usage_of(response: Any) -> Usage:
    usage = response.usage
    return Usage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", None) or 0,
        cache_write_tokens=getattr(usage, "cache_creation_input_tokens", None) or 0,
    )


def classify(error: Exception) -> FailureKind:
    """Most specific first: a timeout IS a connection error in the SDK's hierarchy."""
    if isinstance(error, anthropic.APITimeoutError):
        return FailureKind.timeout
    if isinstance(error, anthropic.APIConnectionError):
        return FailureKind.connection
    if isinstance(error, anthropic.RateLimitError):
        return FailureKind.rate_limited
    if isinstance(error, anthropic.APIStatusError):
        transient = error.status_code in (408, 409) or error.status_code >= 500
        return FailureKind.server_error if transient else FailureKind.client_error
    if isinstance(error, ValidationError):
        return FailureKind.schema_invalid
    if isinstance(error, json.JSONDecodeError):
        return FailureKind.malformed
    return FailureKind.unexpected


def _stopped(response: Any) -> FailureKind | None:
    return _BAD_STOPS.get(response.stop_reason)


def _failed[T](error: Exception, started: float) -> LLMResult[T]:
    """The class name only: an SDK message can echo the request, i.e. candidate text."""
    result: LLMResult[T] = LLMResult(failure=classify(error), error_class=type(error).__name__)
    return _timed(result, started)


def _timed[T](result: LLMResult[T], started: float) -> LLMResult[T]:
    return result.model_copy(update={"latency_ms": round((time.monotonic() - started) * 1000)})
