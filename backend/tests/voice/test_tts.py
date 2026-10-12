"""Spec 013 T1: voice config, the ElevenLabs client (mock transport) and the TTS cache."""

import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from sazon_screening.api.settings import load_app_settings
from sazon_screening.config import ConfigError
from sazon_screening.vocab import Country, Language
from sazon_screening.voice import ElevenLabsClient, TTSService, TTSUnavailable, load_voice_config
from sazon_screening.voice.config import VoiceConfig, VoiceSettings
from tests.paths import SHIPPED_CONFIG_DIR


class FakeTTSClient:
    """Records every call; returns fake mp3 bytes, or raises when `fail` is set."""

    def __init__(self, fail: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail = fail

    async def synthesize(
        self,
        *,
        text: str,
        voice_id: str,
        model_id: str,
        output_format: str,
        voice_settings: VoiceSettings,
    ) -> bytes:
        self.calls.append({"text": text, "voice_id": voice_id, "model_id": model_id})
        if self.fail:
            raise TTSUnavailable("voice provider error (500)")
        return b"ID3" + text.encode()


def config(**overrides: object) -> VoiceConfig:
    data: dict[str, object] = {
        "version": "t",
        "model_id": "eleven_multilingual_v2",
        "voices": {"es": "voice-es", "en": "voice-en", "es-MX": "voice-mx"},
    }
    data.update(overrides)
    return VoiceConfig.model_validate(data)


def test_shipped_voice_config_loads() -> None:
    shipped = load_voice_config(SHIPPED_CONFIG_DIR)
    assert shipped.model_id
    assert shipped.output_format.startswith("mp3_")
    assert shipped.voice_for(Language.es)
    assert shipped.voice_for(Language.en)


def test_voice_config_needs_every_language(tmp_path: Path) -> None:
    (tmp_path / "voice.yaml").write_text(
        "version: x\nmodel_id: m\nvoices: {es: a}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match=r"voice\.yaml: voices: .*en"):
        load_voice_config(tmp_path)


def test_voice_config_rejects_non_mp3_format() -> None:
    with pytest.raises(ValueError, match="mp3"):
        config(output_format="pcm_16000")


def test_register_specific_voice_wins_then_language() -> None:
    voices = config()
    assert voices.voice_for(Language.es, Country.MX) == "voice-mx"
    assert voices.voice_for(Language.es, Country.ES) == "voice-es"
    assert voices.voice_for(Language.en, Country.MX) == "voice-en"


@pytest.mark.anyio
async def test_cache_hit_avoids_a_second_call() -> None:
    client = FakeTTSClient()
    tts = TTSService(config(), client)
    first, cached_first = await tts.speak("Hola", Language.es)
    second, cached_second = await tts.speak("Hola", Language.es)
    assert first == second == b"ID3Hola"
    assert (cached_first, cached_second) == (False, True)
    assert len(client.calls) == 1
    # A different voice is a different entry.
    await tts.speak("Hola", Language.es, Country.MX)
    assert len(client.calls) == 2


@pytest.mark.anyio
async def test_cache_is_lru_and_bounded() -> None:
    client = FakeTTSClient()
    tts = TTSService(config(cache_entries=2), client)
    await tts.speak("a", Language.es)
    await tts.speak("b", Language.es)
    await tts.speak("a", Language.es)  # refresh "a": "b" is now the oldest
    await tts.speak("c", Language.es)  # evicts "b"
    await tts.speak("a", Language.es)
    assert [c["text"] for c in client.calls] == ["a", "b", "c"]
    await tts.speak("b", Language.es)
    assert [c["text"] for c in client.calls] == ["a", "b", "c", "b"]


@pytest.mark.anyio
async def test_no_client_is_unavailable() -> None:
    tts = TTSService(config(), None)
    assert not tts.available
    with pytest.raises(TTSUnavailable, match="ELEVENLABS_API_KEY"):
        await tts.speak("Hola", Language.es)


@pytest.mark.anyio
async def test_voice_override_beats_config() -> None:
    client = FakeTTSClient()
    tts = TTSService(config(), client, voice_override=" custom ")
    await tts.speak("Hola", Language.es, Country.MX)
    assert client.calls[0]["voice_id"] == "custom"


@pytest.mark.anyio
async def test_failures_are_not_cached() -> None:
    client = FakeTTSClient(fail=True)
    tts = TTSService(config(), client)
    for _ in range(2):
        with pytest.raises(TTSUnavailable):
            await tts.speak("Hola", Language.es)
    assert len(client.calls) == 2


# --- ElevenLabsClient against a mock transport (no network) ----------------------------


@pytest.mark.anyio
async def test_elevenlabs_request_shape() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"mp3-bytes", headers={"content-type": "audio/mpeg"})

    client = ElevenLabsClient(
        SecretStr("sk-test"), timeout_seconds=5, transport=httpx.MockTransport(handler)
    )
    audio = await client.synthesize(
        text="Hola, soy Sofi",
        voice_id="voice-es",
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_64",
        voice_settings=VoiceSettings(),
    )
    await client.aclose()
    assert audio == b"mp3-bytes"
    request = seen[0]
    assert request.method == "POST"
    assert request.url.path == "/v1/text-to-speech/voice-es"
    assert request.url.params["output_format"] == "mp3_44100_64"
    assert request.headers["xi-api-key"] == "sk-test"
    body = json.loads(request.content)
    assert body["text"] == "Hola, soy Sofi"
    assert body["model_id"] == "eleven_multilingual_v2"
    assert body["voice_settings"]["stability"] == 0.5


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 404, 429, 500])
async def test_elevenlabs_errors_become_unavailable(
    status: int, caplog: pytest.LogCaptureFixture
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": {"status": "boom"}})

    client = ElevenLabsClient(
        SecretStr("sk-secret-key"), timeout_seconds=5, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(TTSUnavailable, match=str(status)):
        await client.synthesize(
            text="x",
            voice_id="v",
            model_id="m",
            output_format="mp3_44100_64",
            voice_settings=VoiceSettings(),
        )
    assert "sk-secret-key" not in caplog.text


@pytest.mark.anyio
async def test_elevenlabs_network_error_becomes_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    client = ElevenLabsClient(
        SecretStr("k"), timeout_seconds=5, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(TTSUnavailable, match="unreachable"):
        await client.synthesize(
            text="x",
            voice_id="v",
            model_id="m",
            output_format="mp3_44100_64",
            voice_settings=VoiceSettings(),
        )


def test_settings_read_elevenlabs_env() -> None:
    settings = load_app_settings({"ELEVENLABS_API_KEY": " sk-1 ", "ELEVENLABS_VOICE_ID": "v1"})
    assert settings.elevenlabs_api_key is not None
    assert settings.elevenlabs_api_key.get_secret_value() == "sk-1"
    assert settings.elevenlabs_voice_id == "v1"
    assert "sk-1" not in repr(settings)
    empty = load_app_settings({"ELEVENLABS_API_KEY": "  "})
    assert empty.elevenlabs_api_key is None
    assert empty.elevenlabs_voice_id is None
