"""Settings for the HTTP API (spec 004 T1): the LLM settings plus database, env and CORS.

Read from real environment variables only, like the LLM layer: `.env` is loaded by
`uv run --env-file`, never implicitly, so tests can never pick up a real key by accident.
"""

import os
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from sazon_screening.llm.settings import Settings, SettingsError, load_settings
from sazon_screening.whatsapp.settings import WhatsAppSettings, load_whatsapp_settings

AppEnv = Literal["dev", "prod"]
DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./sazon.db"  # relative to where the API runs
DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)  # the Vite dev server


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    llm: Settings = Settings()
    database_url: str = DEFAULT_DATABASE_URL
    app_env: AppEnv = "dev"  # "dev" enables /api/dev/* (seed, silence); deploy with "prod"
    cors_origins: list[str] = list(DEFAULT_CORS_ORIGINS)
    # Spec 008: start the follow-up loop in the lifespan. Off unless loaded from the
    # environment (where it defaults to on), so tests drive the scheduler themselves.
    reengagement_scheduler: bool = False
    reengagement_time_scale: float = Field(1.0, gt=0)  # 60: an hour of schedule per minute
    # Spec 013: Sofi's voice. No key -> the voice page uses the browser's own voice.
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_voice_id: str | None = None  # overrides config/voice.yaml
    # Spec 016: the real WhatsApp channel. Off unless WHATSAPP_ENABLED=true.
    whatsapp: WhatsAppSettings = WhatsAppSettings()


def load_app_settings(environ: Mapping[str, str] = os.environ) -> AppSettings:
    """Read DATABASE_URL, APP_ENV, CORS_ORIGINS (comma-separated), REENGAGEMENT_SCHEDULER
    (on/off), REENGAGEMENT_TIME_SCALE, ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID on top of
    the LLM ones."""
    app_env = environ.get("APP_ENV", "").strip() or "dev"
    if app_env not in ("dev", "prod"):
        raise SettingsError(f"APP_ENV must be 'dev' or 'prod', got {app_env!r}")
    origins = environ.get("CORS_ORIGINS", "").strip()
    scheduler = environ.get("REENGAGEMENT_SCHEDULER", "").strip().lower() or "on"
    if scheduler not in ("on", "off"):
        raise SettingsError(f"REENGAGEMENT_SCHEDULER must be 'on' or 'off', got {scheduler!r}")
    raw_scale = environ.get("REENGAGEMENT_TIME_SCALE", "").strip() or "1"
    try:
        time_scale = float(raw_scale)
    except ValueError:
        raise SettingsError(
            f"REENGAGEMENT_TIME_SCALE must be a number, got {raw_scale!r}"
        ) from None
    if time_scale <= 0:
        raise SettingsError(f"REENGAGEMENT_TIME_SCALE must be positive, got {raw_scale!r}")
    eleven_key = environ.get("ELEVENLABS_API_KEY", "").strip()
    return AppSettings(
        llm=load_settings(environ),
        database_url=environ.get("DATABASE_URL", "").strip() or DEFAULT_DATABASE_URL,
        app_env="prod" if app_env == "prod" else "dev",
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()]
        if origins
        else list(DEFAULT_CORS_ORIGINS),
        reengagement_scheduler=scheduler == "on",
        reengagement_time_scale=time_scale,
        elevenlabs_api_key=SecretStr(eleven_key) if eleven_key else None,
        elevenlabs_voice_id=environ.get("ELEVENLABS_VOICE_ID", "").strip() or None,
        whatsapp=load_whatsapp_settings(environ),
    )
