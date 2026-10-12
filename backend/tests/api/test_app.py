"""T1: settings from the environment, the app factory and the health check."""

import pytest
from httpx import ASGITransport, AsyncClient

from sazon_screening.api.app import create_app
from sazon_screening.api.settings import AppSettings, load_app_settings
from sazon_screening.llm.settings import SettingsError


def test_defaults_are_offline_dev_sqlite_and_vite() -> None:
    settings = load_app_settings({})
    assert settings.llm.llm_mode == "fake"
    assert settings.app_env == "dev"
    assert settings.database_url.startswith("sqlite+aiosqlite:///")
    assert settings.cors_origins == ["http://localhost:5173"]


def test_reads_database_env_and_cors_from_the_environment() -> None:
    settings = load_app_settings(
        {
            "DATABASE_URL": "sqlite+aiosqlite:///tmp.db",
            "APP_ENV": "prod",
            "CORS_ORIGINS": "http://a.test, http://b.test",
        }
    )
    assert settings.database_url == "sqlite+aiosqlite:///tmp.db"
    assert settings.app_env == "prod"
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_unknown_app_env_fails_fast() -> None:
    with pytest.raises(SettingsError, match="APP_ENV"):
        load_app_settings({"APP_ENV": "staging"})


@pytest.mark.anyio
async def test_health_and_cors_preflight() -> None:
    app = create_app(AppSettings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        health = await client.get("/api/health")
        preflight = await client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"
