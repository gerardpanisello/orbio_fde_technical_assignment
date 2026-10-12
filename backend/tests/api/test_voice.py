"""Spec 013 AC-3: the TTS proxy route (fake client, 503 without key, cache), no network."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from sazon_screening.voice import TTSService, load_voice_config
from tests.paths import SHIPPED_CONFIG_DIR
from tests.voice.test_tts import FakeTTSClient


@pytest.fixture
def fake_tts(app: FastAPI) -> FakeTTSClient:
    client = FakeTTSClient()
    app.state.tts = TTSService(load_voice_config(SHIPPED_CONFIG_DIR), client)
    return client


@pytest.mark.anyio
@pytest.mark.ac("013:AC-4")
async def test_without_key_tts_is_503_and_status_says_browser(client: AsyncClient) -> None:
    # The test settings carry no ELEVENLABS_API_KEY.
    response = await client.post("/api/voice/tts", json={"text": "Hola", "language": "es"})
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert "ELEVENLABS_API_KEY" in response.json()["detail"]
    status = await client.get("/api/voice/status")
    assert status.json() == {"tts": "browser", "model_id": None}


@pytest.mark.anyio
@pytest.mark.ac("013:AC-3")
async def test_tts_returns_audio_and_caches(client: AsyncClient, fake_tts: FakeTTSClient) -> None:
    body = {"text": "¿Tienes carné de conducir?", "language": "es", "country": "MX"}
    first = await client.post("/api/voice/tts", json=body)
    assert first.status_code == 200
    assert first.headers["content-type"] == "audio/mpeg"
    assert first.headers["x-tts-cache"] == "miss"
    assert first.content.startswith(b"ID3")
    second = await client.post("/api/voice/tts", json=body)
    assert second.headers["x-tts-cache"] == "hit"
    assert second.content == first.content
    assert len(fake_tts.calls) == 1
    status = await client.get("/api/voice/status")
    assert status.json()["tts"] == "elevenlabs"


@pytest.mark.anyio
@pytest.mark.ac("013:AC-3")
async def test_provider_failure_is_503(client: AsyncClient, fake_tts: FakeTTSClient) -> None:
    fake_tts.fail = True
    response = await client.post("/api/voice/tts", json={"text": "Hola"})
    assert response.status_code == 503
    assert response.json() == {"detail": "voice provider error (500)"}


@pytest.mark.anyio
@pytest.mark.parametrize("text", ["", "   ", "x" * 5000])
async def test_tts_rejects_empty_or_long_text(
    client: AsyncClient, fake_tts: FakeTTSClient, text: str
) -> None:
    response = await client.post("/api/voice/tts", json={"text": text})
    assert response.status_code == 422
    assert fake_tts.calls == []
