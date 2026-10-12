"""Route dependencies: the service (writes) and a DB session (dashboard reads)."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from sazon_screening.api.service import ScreeningService


def get_service(request: Request) -> ScreeningService:
    service: ScreeningService = request.app.state.service
    return service


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        yield session


ServiceDep = Annotated[ScreeningService, Depends(get_service)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
