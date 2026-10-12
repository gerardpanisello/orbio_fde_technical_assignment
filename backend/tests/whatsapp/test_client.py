"""The Graph API client over a mocked HTTP transport (no network), and the settings."""

import json
from pathlib import Path

import httpx
import pytest

from sazon_screening.config import ConfigError
from sazon_screening.llm.settings import SettingsError
from sazon_screening.vocab import Country
from sazon_screening.whatsapp.client import FakeWhatsAppClient, GraphError, GraphWhatsAppClient
from sazon_screening.whatsapp.payloads import read_receipt, text_message
from sazon_screening.whatsapp.settings import (
    WhatsAppSettings,
    load_whatsapp_config,
    load_whatsapp_settings,
)
from tests.paths import SHIPPED_CONFIG_DIR

ENV = {
    "WHATSAPP_ENABLED": "true",
    "WHATSAPP_TOKEN": "graph-token-123",
    "WHATSAPP_PHONE_NUMBER_ID": "123456",
    "WHATSAPP_VERIFY_TOKEN": "verify-me",
    "WHATSAPP_APP_SECRET": "shh",
}


def graph(handler: httpx.MockTransport) -> GraphWhatsAppClient:
    settings = load_whatsapp_settings(ENV)
    return GraphWhatsAppClient(settings, httpx.AsyncClient(transport=handler))


@pytest.mark.anyio
async def test_send_posts_json_with_bearer_token_and_returns_the_message_id() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.ABC"}]})

    client = graph(httpx.MockTransport(handle))
    assert await client.send(text_message("34600000001", "Hola")) == "wamid.ABC"
    request = seen[0]
    assert str(request.url) == "https://graph.facebook.com/v25.0/123456/messages"
    assert request.headers["Authorization"] == "Bearer graph-token-123"
    assert json.loads(request.content)["text"]["body"] == "Hola"
    await client.aclose()


@pytest.mark.anyio
async def test_a_read_receipt_has_no_message_id() -> None:
    client = graph(httpx.MockTransport(lambda _: httpx.Response(200, json={"success": True})))
    assert await client.send(read_receipt("wamid.1")) is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "retryable"), [(500, True), (503, True), (429, True), (400, False), (401, False)]
)
async def test_errors_say_whether_a_retry_can_help(status: int, retryable: bool) -> None:
    body = {"error": {"code": 131030, "message": "Recipient phone number not in allowed list"}}
    client = graph(httpx.MockTransport(lambda _: httpx.Response(status, json=body)))
    with pytest.raises(GraphError) as caught:
        await client.send(text_message("34600000001", "Hola"))
    assert caught.value.retryable is retryable
    assert caught.value.status == status
    assert "131030" in caught.value.detail
    assert "34600000001" not in caught.value.detail


@pytest.mark.anyio
async def test_timeouts_and_network_errors_are_retryable() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    for handler in (timeout, refused):
        with pytest.raises(GraphError) as caught:
            await graph(httpx.MockTransport(handler)).send(text_message("34600000001", "x"))
        assert caught.value.retryable


@pytest.mark.anyio
async def test_fake_records_payloads_and_fails_on_demand() -> None:
    fake = FakeWhatsAppClient()
    fake.fail_next(1)
    with pytest.raises(GraphError):
        await fake.send(text_message("34600000001", "a"))
    assert await fake.send(text_message("34600000001", "b")) == "wamid.fake.1"
    assert await fake.send(read_receipt("wamid.in")) is None
    assert fake.attempts == 3
    assert [m["text"]["body"] for m in fake.messages()] == ["b"]
    assert len(fake.receipts()) == 1


def test_disabled_by_default_and_needs_every_secret_when_enabled() -> None:
    assert load_whatsapp_settings({}).enabled is False
    settings = load_whatsapp_settings(ENV)
    assert settings.enabled
    assert settings.api_version == "v25.0"
    assert "graph-token-123" not in repr(settings)  # secrets never print
    with pytest.raises(SettingsError, match="WHATSAPP_APP_SECRET"):
        load_whatsapp_settings({**ENV, "WHATSAPP_APP_SECRET": ""})
    with pytest.raises(SettingsError, match="WHATSAPP_ENABLED"):
        load_whatsapp_settings({"WHATSAPP_ENABLED": "maybe"})
    assert WhatsAppSettings().enabled is False


def test_shipped_config_and_country_prefixes() -> None:
    config = load_whatsapp_config(SHIPPED_CONFIG_DIR)
    assert config.follow_up_template.name == "hello_world"
    assert config.follow_up_template.placeholder
    assert config.country_for("34600000001") is Country.ES
    assert config.country_for("5215512345678") is Country.MX
    assert config.country_for("447700900000") is None


def test_config_errors_name_the_problem(tmp_path: Path) -> None:
    text = (SHIPPED_CONFIG_DIR / "whatsapp.yaml").read_text(encoding="utf-8")
    (tmp_path / "whatsapp.yaml").write_text(
        text.replace('es: "Ver opciones"', 'es: "Ver todas las opciones disponibles"'),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="list_button"):
        load_whatsapp_config(tmp_path)
