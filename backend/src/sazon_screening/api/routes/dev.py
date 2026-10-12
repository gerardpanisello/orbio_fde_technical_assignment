"""Dev-only routes (FR-12, FR-13): demo data and demo controls for re-engagement (008).

They answer 403 unless APP_ENV=dev, so a deployed API never exposes them.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request

from sazon_screening.api import seed as demo
from sazon_screening.api.deps import ServiceDep
from sazon_screening.api.schemas import AdvanceOut, SeedOut, TurnOut
from sazon_screening.api.service import NotAllowed, ScreeningService
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


@router.post("/conversations/{conversation_id}/advance")
async def advance(
    conversation_id: str, service: ServiceDep, background: BackgroundTasks
) -> AdvanceOut:
    """Spec 008 FR-8: run the NEXT re-engagement step now (the next reminder, or the
    abandon after the last one), as if its time had come. Exactly one step per call.
    409 when there is nothing to advance (closed, opted out, the candidate wrote last,
    or re-engagement is disabled)."""
    outcome = await service.reengage(conversation_id, force=True)
    if outcome.action == "none":
        raise NotAllowed(f"nothing to advance: {outcome.reason}")
    if outcome.summary_due:
        background.add_task(service.write_summary, conversation_id)
    return AdvanceOut.of(outcome, await service.next_reengagement(conversation_id))


@router.post("/conversations/{conversation_id}/silence")
async def silence(
    conversation_id: str, service: ServiceDep, background: BackgroundTasks
) -> TurnOut:
    """Kept from 004: `silence_expired` at once, skipping the reminders (straight to
    `abandoned`). Use `/advance` to walk through the reminders first."""
    outcome = await service.send_event(conversation_id, SilenceExpired())
    if outcome.result.summary_due:
        background.add_task(service.write_summary, conversation_id)
    return TurnOut.of(outcome)
