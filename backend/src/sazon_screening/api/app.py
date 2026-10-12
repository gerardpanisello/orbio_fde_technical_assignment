"""The FastAPI app (spec 004). Start here: `create_app` wires settings, DB, agent and routes.

Run it (from backend/):

    uv run uvicorn sazon_screening.api.app:create_app --factory --reload

A factory, not a module-level `app`, so importing this module never reads the
environment or opens a database (tests build their own app with a temp DB).
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sazon_screening.api.db import create_tables, make_engine, make_sessions
from sazon_screening.api.routes import analytics, candidates, conversations, dev, meta, zones
from sazon_screening.api.routes.voice import router as voice_router
from sazon_screening.api.service import (
    Clock,
    ConversationNotFound,
    NotAllowed,
    ScreeningService,
    utc_now,
)
from sazon_screening.api.settings import AppSettings, load_app_settings
from sazon_screening.api.slots import load_slot_provider
from sazon_screening.config import load_zone_staffing
from sazon_screening.llm.pipeline import ScreeningAgent, build_agent
from sazon_screening.reengagement import load_reengagement
from sazon_screening.reengagement.scheduler import ReengagementScheduler

logger = logging.getLogger("sazon_screening.api")


def create_app(
    settings: AppSettings | None = None,
    *,
    agent: ScreeningAgent | None = None,
    clock: Clock = utc_now,
) -> FastAPI:
    """`agent` and `clock` are for tests; by default both come from settings and the system."""
    settings = settings or load_app_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Everything that can fail on bad config fails here, at startup.
        engine = make_engine(settings.database_url)
        await create_tables(engine)
        app.state.sessions = make_sessions(engine)
        screening_agent = agent or build_agent(settings.llm)
        areas = screening_agent.engine_config.service_areas
        reengagement = load_reengagement(settings.llm.config_dir, areas)
        app.state.service = ScreeningService(
            screening_agent,
            app.state.sessions,
            load_slot_provider(settings.llm.config_dir),
            clock,
            load_zone_staffing(settings.llm.config_dir, areas),
            reengagement.scaled(settings.reengagement_time_scale),
        )
        await app.state.service.init_zone_staffing()  # spec 015: only into an empty table
        # Spec 008: the follow-up loop. Tests leave it off and call `tick()` themselves.
        app.state.scheduler = ReengagementScheduler(
            app.state.service, tick_seconds=reengagement.tick_seconds
        )
        loop = None
        if settings.reengagement_scheduler and reengagement.enabled:
            loop = asyncio.create_task(app.state.scheduler.run(), name="reengagement")
        yield
        if loop is not None:
            loop.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await loop
        await engine.dispose()

    app = FastAPI(title="Grupo Sazón screening API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(ConversationNotFound, _not_found)
    app.add_exception_handler(NotAllowed, _conflict)
    app.add_exception_handler(Exception, _unexpected_error)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "llm_mode": settings.llm.llm_mode, "env": settings.app_env}

    app.include_router(conversations.router)
    app.include_router(candidates.router)
    app.include_router(analytics.router)
    app.include_router(zones.router)
    app.include_router(meta.router)
    app.include_router(dev.router)
    app.include_router(voice_router)  # spec 013
    return app


async def _not_found(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Conversation not found"})


async def _conflict(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(error)})


async def _unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """FR-15: a 500 with no stack trace for the client, the full one in the log."""
    conversation_id = request.path_params.get("conversation_id", "-")
    logger.error(
        "unexpected error on %s %s (conversation %s)",
        request.method,
        request.url.path,
        conversation_id,
        exc_info=error,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
