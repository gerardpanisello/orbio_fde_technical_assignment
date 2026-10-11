"""T26: the Anthropic client's pure parts and failure handling, all offline (FR-23, NFR-7)."""

import json
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import BaseModel, ValidationError

from sazon_screening.llm.client.anthropic_client import (
    AnthropicClient,
    build_kwargs,
    classify,
    interpret_parsed,
    interpret_text,
)
from sazon_screening.llm.client.base import Effort, FailureKind, LLMRequest, Role, Usage

REQUEST = LLMRequest(
    role=Role.extraction,
    model="claude-haiku-5-5",
    prompt_id="extraction.v1",
    prompt_sha="abc",
    system="static system prompt",
    user="<candidate_message>hola</candidate_message>",
    max_tokens=512,
    effort=Effort.low,
    timeout_s=6,
)
HTTP_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


class Small(BaseModel):
    x: int


def usage(**tokens: int) -> SimpleNamespace:
    base = {
        "input_tokens": 120,
        "output_tokens": 30,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    return SimpleNamespace(**(base | tokens))


def response(stop_reason: str = "end_turn", **fields: Any) -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop_reason, usage=usage(), **fields)


def status_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    return cls("boom", response=httpx2.Response(status, request=HTTP_REQUEST), body=None)


class TestBuildKwargs:
    @pytest.mark.ac("003:AC-25")
    def test_cacheable_system_one_user_message_and_effort(self) -> None:
        kwargs = build_kwargs(REQUEST)
        assert kwargs["system"] == [
            {"type": "text", "text": "static system prompt", "cache_control": {"type": "ephemeral"}}
        ]
        assert kwargs["messages"] == [{"role": "user", "content": REQUEST.user}]
        assert kwargs["messages"][-1]["role"] != "assistant"  # no prefill (400 on these models)
        assert kwargs["output_config"] == {"effort": "low"}
        assert (kwargs["model"], kwargs["max_tokens"]) == ("claude-haiku-5-5", 512)

    def test_the_fake_only_payload_is_never_sent(self) -> None:
        kwargs = build_kwargs(REQUEST.model_copy(update={"payload": Small(x=1)}))
        assert "payload" not in json.dumps(kwargs)
        assert "timeout_s" not in kwargs


class TestInterpret:
    @pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
    def test_a_bad_stop_reason_fails_before_content_is_read(self, stop: str) -> None:
        class Explodes:
            def __getattr__(self, name: str) -> Any:
                raise AssertionError("content must not be read")

        parsed = interpret_parsed(response(stop, parsed_output=Explodes()), Small)
        text = interpret_text(response(stop, content=Explodes()))
        assert (parsed.failure, text.failure) == (FailureKind(stop), FailureKind(stop))
        assert parsed.stop_reason == stop

    def test_no_parsed_output_is_malformed(self) -> None:
        assert (
            interpret_parsed(response(parsed_output=None), Small).failure is FailureKind.malformed
        )

    def test_a_parsed_object_of_another_type_is_schema_invalid(self) -> None:
        result = interpret_parsed(response(parsed_output={"x": 1}), Small)
        assert result.failure is FailureKind.schema_invalid

    def test_parsed_output_and_usage(self) -> None:
        reply = response(parsed_output=Small(x=3))
        reply.usage = usage(cache_read_input_tokens=900, cache_creation_input_tokens=50)
        result = interpret_parsed(reply, Small)
        assert result.ok
        assert result.value == Small(x=3)
        assert result.usage == Usage(
            input_tokens=120, output_tokens=30, cache_read_tokens=900, cache_write_tokens=50
        )

    def test_text_blocks_are_joined_and_thinking_ignored(self) -> None:
        content = [
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text="¡Hola! "),
            SimpleNamespace(type="text", text="¿Cómo te llamas?"),
        ]
        assert interpret_text(response(content=content)).value == "¡Hola! ¿Cómo te llamas?"

    def test_no_text_is_empty(self) -> None:
        assert interpret_text(response(content=[])).failure is FailureKind.empty

    def test_missing_cache_fields_count_as_zero(self) -> None:
        reply = response(content=[SimpleNamespace(type="text", text="ok")])
        reply.usage = SimpleNamespace(input_tokens=5, output_tokens=1)
        assert interpret_text(reply).usage == Usage(input_tokens=5, output_tokens=1)


def _validation_error() -> ValidationError:
    try:
        Small.model_validate({"x": {}})
    except ValidationError as error:
        return error
    raise AssertionError("unreachable")


@pytest.mark.ac("003:AC-4")
@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (anthropic.APITimeoutError(request=HTTP_REQUEST), FailureKind.timeout),
        (anthropic.APIConnectionError(request=HTTP_REQUEST), FailureKind.connection),
        (status_error(anthropic.RateLimitError, 429), FailureKind.rate_limited),
        (status_error(anthropic.InternalServerError, 500), FailureKind.server_error),
        (status_error(anthropic.APIStatusError, 529), FailureKind.server_error),
        (status_error(anthropic.APIStatusError, 408), FailureKind.server_error),
        (status_error(anthropic.BadRequestError, 400), FailureKind.client_error),
        (status_error(anthropic.AuthenticationError, 401), FailureKind.client_error),
        (_validation_error(), FailureKind.schema_invalid),
        (json.JSONDecodeError("bad", "{", 0), FailureKind.malformed),
        (RuntimeError("our bug"), FailureKind.unexpected),
    ],
    ids=lambda value: type(value).__name__,
)
def test_classify(error: Exception, kind: FailureKind) -> None:
    assert classify(error) is kind


class FakeMessages:
    def __init__(self, error: Exception | None = None, result: Any = None) -> None:
        self.error, self.result, self.kwargs = error, result, {}

    async def parse(self, **kwargs: Any) -> Any:
        return await self.create(**kwargs)

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.anyio
async def test_an_sdk_exception_becomes_a_failure_with_its_class_name() -> None:
    messages = FakeMessages(error=anthropic.APITimeoutError(request=HTTP_REQUEST))
    client = AnthropicClient(sdk=SimpleNamespace(messages=messages))
    result = await client.parse(REQUEST, Small)
    assert (result.failure, result.error_class) == (FailureKind.timeout, "APITimeoutError")
    assert messages.kwargs["timeout"] == 6
    assert messages.kwargs["output_format"] is Small


@pytest.mark.anyio
async def test_text_call_returns_the_reply() -> None:
    reply = response(content=[SimpleNamespace(type="text", text="¿Cuántos años tienes?")])
    client = AnthropicClient(sdk=SimpleNamespace(messages=FakeMessages(result=reply)))
    result = await client.text(REQUEST)
    assert result.value == "¿Cuántos años tienes?"
    assert client.name == "anthropic"
