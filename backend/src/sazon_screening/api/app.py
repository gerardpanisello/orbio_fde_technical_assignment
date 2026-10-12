"""The FastAPI app (spec 004). Start here: `create_app` wires settings, DB, agent and routes.

Run it (from backend/):

    uv run uvicorn sazon_screening.api.app:create_app --factory --reload

A factory, not a module-level `app`, so importing this module never reads the
environment or opens a database (tests build their own app with a temp DB).
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sazon_screening.api.settings import AppSettings, load_app_settings

logger = logging.getLogger("sazon_screening.api")


def create_app(settings: AppSettings | None = None) -> FastAPI:
    settings = settings or load_app_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(title="Grupo Sazón screening API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(Exception, _unexpected_error)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "llm_mode": settings.llm.llm_mode, "env": settings.app_env}

    return app


async def _unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """FR-15: a 500 with no stack trace for the client, the full one in the log."""
    conversation_id = request.path_params.get("conversation_id", "-")
    logger.exception(
        "unexpected error on %s %s (conversation %s)",
        request.method,
        request.url.path,
        conversation_id,
        exc_info=error,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
