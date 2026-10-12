"""Voice channel (spec 013): Sofi's text-to-speech through our backend.

The browser does speech-to-text itself and sends turns to the normal conversation
endpoints, so the only voice-specific route is this proxy to ElevenLabs. The key stays
on the server; any failure is a 503 and the page falls back to the browser's voice.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from sazon_screening.api.settings import AppSettings
from sazon_screening.vocab import Country, Language
from sazon_screening.voice import (
    ElevenLabsClient,
    TTSService,
    TTSUnavailable,
    load_voice_config,
)

router = APIRouter(prefix="/api/voice", tags=["voice"])


def get_tts(request: Request) -> TTSService:
    """Built on first use (not at startup), so a bad voice.yaml never stops the chat API.

    Tests put their own `TTSService` (with a fake client) on `app.state.tts`.
    """
    tts: TTSService | None = getattr(request.app.state, "tts", None)
    if tts is None:
        settings: AppSettings = request.app.state.settings
        config = load_voice_config(settings.llm.config_dir)
        client = (
            ElevenLabsClient(settings.elevenlabs_api_key, timeout_seconds=config.timeout_seconds)
            if settings.elevenlabs_api_key
            else None
        )
        tts = TTSService(config, client, voice_override=settings.elevenlabs_voice_id)
        request.app.state.tts = tts
    return tts


TTSDep = Annotated[TTSService, Depends(get_tts)]


class TTSIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    language: Language = Language.es
    # The candidate's country (Spain/Mexico register): picks an "es-MX" voice if configured.
    country: Country | None = None


class VoiceStatus(BaseModel):
    """`elevenlabs` when a key is configured; `browser` means use speechSynthesis."""

    tts: Literal["elevenlabs", "browser"]
    model_id: str | None


@router.get("/status")
async def voice_status(tts: TTSDep) -> VoiceStatus:
    """Lets the page show "voz: ElevenLabs / navegador" and skip doomed TTS calls."""
    if tts.available:
        return VoiceStatus(tts="elevenlabs", model_id=tts.config.model_id)
    return VoiceStatus(tts="browser", model_id=None)


@router.post(
    "/tts",
    response_class=Response,
    responses={
        200: {"content": {"audio/mpeg": {}}, "description": "Sofi's voice (mp3)"},
        503: {"description": "No key or the provider failed: use the browser voice"},
    },
)
async def text_to_speech(body: TTSIn, tts: TTSDep) -> Response:
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text is empty")
    if len(text) > tts.config.max_text_chars:
        raise HTTPException(
            status_code=422, detail=f"text longer than {tts.config.max_text_chars} characters"
        )
    try:
        audio, cached = await tts.speak(text, body.language, body.country)
    except TTSUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from None
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"X-TTS-Cache": "hit" if cached else "miss", "Cache-Control": "no-store"},
    )
