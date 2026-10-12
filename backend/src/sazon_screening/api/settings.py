"""Settings for the HTTP API (spec 004 T1): the LLM settings plus database, env and CORS.

Read from real environment variables only, like the LLM layer: `.env` is loaded by
`uv run --env-file`, never implicitly, so tests can never pick up a real key by accident.
"""

import os
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sazon_screening.llm.settings import Settings, SettingsError, load_settings

AppEnv = Literal["dev", "prod"]
DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./sazon.db"  # relative to where the API runs
DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)  # the Vite dev server


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    llm: Settings = Settings()
    database_url: str = DEFAULT_DATABASE_URL
    app_env: AppEnv = "dev"  # "dev" enables /api/dev/* (seed, silence); deploy with "prod"
    cors_origins: list[str] = list(DEFAULT_CORS_ORIGINS)


def load_app_settings(environ: Mapping[str, str] = os.environ) -> AppSettings:
    """Read DATABASE_URL, APP_ENV and CORS_ORIGINS (comma-separated) on top of the LLM ones."""
    app_env = environ.get("APP_ENV", "").strip() or "dev"
    if app_env not in ("dev", "prod"):
        raise SettingsError(f"APP_ENV must be 'dev' or 'prod', got {app_env!r}")
    origins = environ.get("CORS_ORIGINS", "").strip()
    return AppSettings(
        llm=load_settings(environ),
        database_url=environ.get("DATABASE_URL", "").strip() or DEFAULT_DATABASE_URL,
        app_env="prod" if app_env == "prod" else "dev",
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()]
        if origins
        else list(DEFAULT_CORS_ORIGINS),
    )
