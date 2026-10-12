"""Text-to-speech proxy to ElevenLabs (spec 013 FR-5).

The browser never sees the key: it posts text to our API, which asks ElevenLabs for
the audio. Identical (voice, model, text) requests are answered from an in-memory LRU
cache, so the prompts every candidate hears ("¿Tienes carné?") cost credits once.
Anything that goes wrong becomes `TTSUnavailable`; the route answers 503 and the page
switches to the browser's own voice.
"""

import logging
from collections import OrderedDict
from typing import Protocol

import httpx
from pydantic import SecretStr

from sazon_screening.vocab import Country, Language
from sazon_screening.voice.config import VoiceConfig, VoiceSettings

logger = logging.getLogger("sazon_screening.voice")

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"


class TTSUnavailable(Exception):  # noqa: N818 - reads as "TTS is unavailable"
    """No audio this time (no key, provider error, timeout). Safe to show to the client."""


class TTSClient(Protocol):
    async def synthesize(
        self,
        *,
        text: str,
        voice_id: str,
        model_id: str,
        output_format: str,
        voice_settings: VoiceSettings,
    ) -> bytes: ...


class ElevenLabsClient:
    """`POST /v1/text-to-speech/{voice_id}` with the `xi-api-key` header; returns mp3 bytes."""

    def __init__(
        self,
        api_key: SecretStr,
        *,
        timeout_seconds: float,
        base_url: str = ELEVENLABS_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,  # tests: httpx.MockTransport
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"xi-api-key": api_key.get_secret_value(), "accept": "audio/mpeg"},
            transport=transport,
        )

    async def synthesize(
        self,
        *,
        text: str,
        voice_id: str,
        model_id: str,
        output_format: str,
        voice_settings: VoiceSettings,
    ) -> bytes:
        try:
            response = await self._client.post(
                f"/v1/text-to-speech/{voice_id}",
                params={"output_format": output_format},
                json={
                    "text": text,
                    "model_id": model_id,
                    "voice_settings": voice_settings.model_dump(),
                },
            )
        except httpx.HTTPError as error:
            logger.warning("ElevenLabs request failed: %s", type(error).__name__)
            raise TTSUnavailable("voice provider unreachable") from None
        if response.status_code != 200 or not response.content:
            # The body names the cause (bad key, unknown voice, quota); log it, never the key.
            logger.warning("ElevenLabs answered %s: %s", response.status_code, response.text[:300])
            raise TTSUnavailable(f"voice provider error ({response.status_code})")
        return response.content

    async def aclose(self) -> None:
        await self._client.aclose()


class TTSService:
    """Picks the voice, enforces the length cap and caches audio (LRU, in memory)."""

    def __init__(
        self,
        config: VoiceConfig,
        client: TTSClient | None,
        *,
        voice_override: str | None = None,
    ) -> None:
        self.config = config
        self._client = client
        self._voice_override = voice_override.strip() if voice_override else None
        self._cache: OrderedDict[tuple[str, str, str], bytes] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @property
    def available(self) -> bool:
        """False without a key: the page goes straight to the browser voice."""
        return self._client is not None

    def voice_id(self, language: Language, register: Country | None) -> str:
        return self._voice_override or self.config.voice_for(language, register)

    async def speak(
        self, text: str, language: Language, register: Country | None = None
    ) -> tuple[bytes, bool]:
        """(mp3 bytes, served from cache)."""
        if self._client is None:
            raise TTSUnavailable("ELEVENLABS_API_KEY is not set")
        voice = self.voice_id(language, register)
        key = (voice, self.config.model_id, text)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            self.hits += 1
            return cached, True
        audio = await self._client.synthesize(
            text=text,
            voice_id=voice,
            model_id=self.config.model_id,
            output_format=self.config.output_format,
            voice_settings=self.config.voice_settings,
        )
        self.misses += 1
        if self.config.cache_entries > 0:
            self._cache[key] = audio
            while len(self._cache) > self.config.cache_entries:
                self._cache.popitem(last=False)
        return audio, False
