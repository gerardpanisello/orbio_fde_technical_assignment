"""Database engine and sessions (SQLAlchemy 2 async, ADR 0007).

SQLite by default; Postgres by changing `DATABASE_URL` (e.g. `postgresql+asyncpg://...`).
Tables are created at startup with `create_all`: no Alembic yet (noted as an improvement).
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sazon_screening.api.models import Base

Sessions = async_sessionmaker[AsyncSession]


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url)


def make_sessions(engine: AsyncEngine) -> Sessions:
    # expire_on_commit=False: rows stay readable after commit, outside the session.
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
