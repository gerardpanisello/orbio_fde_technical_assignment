"""Dev-only routes (FR-12, FR-13): demo data and a stand-in for the silence timer (008).

They answer 403 unless APP_ENV=dev, so a deployed API never exposes them.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request

from sazon_screening.api import seed as demo
from sazon_screening.api.deps import ServiceDep
from sazon_screening.api.schemas import SeedOut, TurnOut
from sazon_screening.api.service import ScreeningService
from sazon_screening.engine import SilenceExpired
from sazon_screening.llm.pipeline import build_agent


def require_dev(request: Request) -> None:
    if request.app.state.settings.app_env != "dev":
        raise HTTPException(status_code=403, detail="Only available with APP_ENV=dev")


router = APIRouter(prefix="/api/dev", tags=["dev"], dependencies=[Depends(require_dev)])


@router.post("/seed", status_code=201)
async def seed(
    request: Request,
    service: ServiceDep,
    n: Annotated[int, Query(ge=1, le=500)] = 40,
    seed: int = 42,
    mode: Literal["fake"] | None = None,
) -> SeedOut:
    """Seed through the server's own agent: the real model when the API runs with
    `LLM_MODE=anthropic`, so the dashboard shows real summaries and costs. `?mode=fake`
    seeds offline with the rules agent instead (free, deterministic)."""
    if mode == "fake":
        service = _offline(request, service)
    ids = await demo.seed(service, n, seed=seed, now=service.now())
    return SeedOut(created=len(ids), ids=ids)


def _offline(request: Request, service: ScreeningService) -> ScreeningService:
    """The rules agent on the same database, built once per app and reused."""
    offline: ScreeningService | None = getattr(request.app.state, "offline_service", None)
    if offline is None:
        llm = request.app.state.settings.llm.model_copy(update={"llm_mode": "fake"})
        offline = service.with_agent(build_agent(llm))
        request.app.state.offline_service = offline
    return offline


@router.post("/conversations/{conversation_id}/silence")
async def silence(
    conversation_id: str, service: ServiceDep, background: BackgroundTasks
) -> TurnOut:
    outcome = await service.send_event(conversation_id, SilenceExpired())
    if outcome.result.summary_due:
        background.add_task(service.write_summary, conversation_id)
    return TurnOut.of(outcome)
