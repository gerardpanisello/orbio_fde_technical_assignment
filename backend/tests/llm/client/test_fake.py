"""T7: the scripted fake client returns canned outcomes, including every failure (FR-24)."""

import pytest
from pydantic import BaseModel

from sazon_screening.llm.client.base import (
    Effort,
    FailureKind,
    LLMRequest,
    Role,
    Usage,
)
from sazon_screening.llm.client.fake import FakeLLMClient, Scripted
from tests.llm.support import FakeClock


class Small(BaseModel):
    x: int | None = None


def request(role: Role = Role.extraction, user: str = "hola") -> LLMRequest:
    return LLMRequest(
        role=role,
        model="claude-haiku-5-5",
        prompt_id="extraction.v1",
        prompt_sha="abc123",
        system="static system prompt",
        user=user,
        max_tokens=100,
        effort=Effort.low,
        timeout_s=6,
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def fake(clock: FakeClock) -> FakeLLMClient:
    return FakeLLMClient(mode="scripted", clock=clock)


@pytest.mark.anyio
@pytest.mark.parametrize("kind", list(FailureKind))
async def test_every_failure_kind_round_trips(fake: FakeLLMClient, kind: FailureKind) -> None:
    fake.push(Role.extraction, Scripted(failure=kind), Scripted(failure=kind))
    parsed = await fake.parse(request(), Small)
    text = await fake.text(request())
    assert (parsed.failure, text.failure) == (kind, kind)
    assert not parsed.ok
    assert parsed.value is None


@pytest.mark.anyio
async def test_parse_returns_the_scripted_object(fake: FakeLLMClient) -> None:
    fake.push(Role.extraction, Scripted(value=Small(x=3)), Scripted(value={"x": 4}))
    assert (await fake.parse(request(), Small)).value == Small(x=3)
    assert (await fake.parse(request(), Small)).value == Small(x=4)


@pytest.mark.anyio
async def test_raw_json_that_does_not_fit_the_schema_is_schema_invalid(
    fake: FakeLLMClient,
) -> None:
    fake.push(Role.extraction, Scripted(raw_json='{"x": {}}'), Scripted(raw_json='{"x": 7}'))
    assert (await fake.parse(request(), Small)).failure is FailureKind.schema_invalid
    assert (await fake.parse(request(), Small)).value == Small(x=7)


@pytest.mark.anyio
async def test_raw_text_that_is_not_json_is_malformed(fake: FakeLLMClient) -> None:
    fake.push(Role.extraction, Scripted(raw_json="{not json"))
    assert (await fake.parse(request(), Small)).failure is FailureKind.malformed


@pytest.mark.anyio
async def test_text_returns_the_scripted_string(fake: FakeLLMClient) -> None:
    fake.push(Role.phrasing, Scripted(value="¡Hola! ¿Cómo te llamas?"))
    result = await fake.text(request(Role.phrasing))
    assert result.ok
    assert result.value == "¡Hola! ¿Cómo te llamas?"
    assert result.stop_reason == "end_turn"


@pytest.mark.anyio
async def test_nothing_scripted_and_no_failure_is_empty(fake: FakeLLMClient) -> None:
    fake.push(Role.phrasing, Scripted())
    assert (await fake.text(request(Role.phrasing))).failure is FailureKind.empty


@pytest.mark.anyio
async def test_requests_are_recorded_in_order(fake: FakeLLMClient) -> None:
    fake.push(Role.extraction, Scripted(value=Small()))
    fake.push(Role.phrasing, Scripted(value="hola"))
    await fake.parse(request(user="first"), Small)
    await fake.text(request(Role.phrasing, user="second"))
    assert [(c.role, c.user) for c in fake.calls] == [
        (Role.extraction, "first"),
        (Role.phrasing, "second"),
    ]


@pytest.mark.anyio
async def test_usage_and_latency_are_reported(fake: FakeLLMClient, clock: FakeClock) -> None:
    usage = Usage(input_tokens=500, output_tokens=40, cache_read_tokens=450)
    fake.push(Role.extraction, Scripted(value=Small(), usage=usage, latency_s=0.8))
    result = await fake.parse(request(), Small)
    assert (result.usage, result.latency_ms) == (usage, 800)
    assert clock.now == pytest.approx(0.8)


@pytest.mark.anyio
async def test_timeout_consumes_the_request_timeout(fake: FakeLLMClient, clock: FakeClock) -> None:
    fake.push(Role.extraction, Scripted(failure=FailureKind.timeout))
    result = await fake.parse(request(), Small)
    assert result.latency_ms == 6000
    assert clock.now == 6


@pytest.mark.anyio
async def test_an_empty_queue_fails_the_test_loudly(fake: FakeLLMClient) -> None:
    with pytest.raises(AssertionError, match="nothing scripted for extraction"):
        await fake.parse(request(), Small)


def test_script_can_be_given_up_front() -> None:
    fake = FakeLLMClient(mode="scripted", script={Role.summary: [Scripted(value="x")]})
    assert fake.name == "fake-scripted"
    assert fake.pending(Role.summary) == 1


def test_rules_mode_is_not_built_yet() -> None:
    with pytest.raises(NotImplementedError):
        FakeLLMClient(mode="rules")
