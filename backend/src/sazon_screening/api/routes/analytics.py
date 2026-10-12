"""Funnel analytics for the dashboard (FR-11)."""

from fastapi import APIRouter

from sazon_screening.api.analytics import build_analytics
from sazon_screening.api.deps import SessionDep
from sazon_screening.api.schemas import Analytics

router = APIRouter(prefix="/api/analytics", tags=["recruiter dashboard"])


@router.get("")
async def get_analytics(session: SessionDep) -> Analytics:
    return await build_analytics(session)
