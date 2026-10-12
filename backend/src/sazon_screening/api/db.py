"""Database engine and sessions (SQLAlchemy 2 async, ADR 0007).

SQLite by default; Postgres by changing `DATABASE_URL` (e.g. `postgresql+asyncpg://...`).
Tables are created at startup with `create_all`: no Alembic yet (noted as an improvement).
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sazon_screening.api.models import Base

log = logging.getLogger(__name__)

Sessions = async_sessionmaker[AsyncSession]


def make_engine(database_url: str) -> AsyncEngine:
    engine = create_async_engine(database_url)
    if engine.dialect.name == "sqlite":
        event.listen(engine.sync_engine, "connect", _sqlite_pragmas)
    return engine


def _sqlite_pragmas(connection: Any, _record: Any) -> None:
    """WAL: readers do not wait for a writer, and commits are much cheaper. Enforce FKs."""
    cursor = connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_sessions(engine: AsyncEngine) -> Sessions:
    # expire_on_commit=False: rows stay readable after commit, outside the session.
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


class StaleSchemaError(RuntimeError):
    """The database was created by an older version (no migrations yet: see the README)."""


def _missing_columns(connection: Connection) -> list[str]:
    """`table.column` pairs the models expect but an existing table lacks."""
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())
    missing: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue  # create_all adds whole new tables by itself
        have = {column["name"] for column in inspector.get_columns(table.name)}
        missing += [f"{table.name}.{c.name}" for c in table.columns if c.name not in have]
    return missing


async def prepare_database(database_url: str, *, reset_stale_sqlite: bool) -> AsyncEngine:
    """Engine with an up-to-date schema.

    `create_all` adds new tables but never new columns, so a database from an older version
    fails on the first query. Without migrations (Alembic is a listed improvement) we check
    up front: in dev a stale SQLite file is renamed to `*.bak-<timestamp>` and recreated;
    otherwise startup stops with a readable message instead of a crash on the first request.
    """
    engine = make_engine(database_url)
    async with engine.connect() as connection:
        missing = await connection.run_sync(_missing_columns)
    if missing:
        database = engine.url.database
        is_file = engine.dialect.name == "sqlite" and database not in (None, "", ":memory:")
        if not (reset_stale_sqlite and is_file and database):
            await engine.dispose()
            raise StaleSchemaError(
                f"database schema is out of date (missing {', '.join(missing[:5])}). "
                "Delete the SQLite file or migrate the database, then restart."
            )
        await engine.dispose()
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        for suffix in ("", "-wal", "-shm"):
            old = Path(database + suffix)
            if old.exists():
                old.rename(old.with_name(f"{old.name}.bak-{stamp}"))
        log.warning(
            "database schema was out of date (missing %s): moved %s to *.bak-%s, starting fresh",
            ", ".join(missing[:5]),
            database,
            stamp,
        )
        engine = make_engine(database_url)
    await create_tables(engine)
    return engine
