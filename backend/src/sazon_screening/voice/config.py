"""`config/voice.yaml`: Sofi's text-to-speech voice (spec 013 FR-5)."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sazon_screening.config import load_yaml_model
from sazon_screening.vocab import CORE_LANGUAGES, Country, Language

VOICE_FILE = "voice.yaml"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VoiceSettings(_Frozen):
    """ElevenLabs per-request `voice_settings` (sent as is)."""

    stability: float = Field(0.5, ge=0, le=1)
    similarity_boost: float = Field(0.75, ge=0, le=1)
    style: float = Field(0.0, ge=0, le=1)
    speed: float = Field(1.0, ge=0.7, le=1.2)


class VoiceConfig(_Frozen):
    version: str
    model_id: str = Field(min_length=1)
    # Per-language model, for a language `model_id` does not speak (spec 017: Catalan
    # needs eleven_v4_turbo or eleven_v3; eleven_multilingual_v2 has no Catalan).
    models: dict[Language, str] = {}
    output_format: str = "mp3_44100_64"
    # "es", "en", and optionally "ca" and "es-MX"-style keys for a country register.
    voices: dict[str, str]
    voice_settings: VoiceSettings = VoiceSettings()
    max_text_chars: int = Field(1200, gt=0)
    cache_entries: int = Field(256, ge=0)
    timeout_seconds: float = Field(12, gt=0)

    @field_validator("output_format")
    @classmethod
    def _mp3_only(cls, value: str) -> str:
        """The endpoint answers audio/mpeg, so only the mp3 formats make sense."""
        if not value.startswith("mp3_"):
            raise ValueError("must be an mp3 format, e.g. mp3_44100_64")
        return value

    @field_validator("voices")
    @classmethod
    def _every_language(cls, voices: dict[str, str]) -> dict[str, str]:
        missing = [lang.value for lang in CORE_LANGUAGES if not voices.get(lang.value, "").strip()]
        if missing:
            raise ValueError(f"needs a voice id for {', '.join(missing)}")
        return voices

    def voice_for(self, language: Language, register: Country | None = None) -> str:
        """The most specific voice: "es-MX" first, then "es" (Catalan: "ca", then "es")."""
        if register is not None:
            specific = self.voices.get(f"{language.value}-{register.value}", "").strip()
            if specific:
                return specific
        own = self.voices.get(language.value, "").strip()
        return own or self.voices[language.fallback.value].strip()

    def model_for(self, language: Language) -> str:
        return self.models.get(language, "").strip() or self.model_id


def load_voice_config(config_dir: Path) -> VoiceConfig:
    return load_yaml_model(config_dir / VOICE_FILE, VoiceConfig)
