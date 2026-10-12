"""A database from an older version must never crash the first request (found in manual
testing: `no such column: conversations.last_candidate_at` on every chat)."""

import sqlite3
from pathlib import Path

import pytest

from sazon_screening.api.db import StaleSchemaError, prepare_database


def _old_database(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY, status TEXT)")
        db.execute("INSERT INTO conversations VALUES ('old', 'in_progress')")


def _url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


@pytest.mark.anyio
async def test_dev_moves_a_stale_sqlite_file_aside_and_starts_fresh(tmp_path: Path) -> None:
    path = tmp_path / "sazon.db"
    _old_database(path)
    engine = await prepare_database(_url(path), reset_stale_sqlite=True)
    await engine.dispose()
    backups = list(tmp_path.glob("sazon.db.bak-*"))
    assert len(backups) == 1  # the old data is kept, never deleted
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(conversations)")}
    assert "last_candidate_at" in columns


@pytest.mark.anyio
async def test_outside_dev_a_stale_schema_stops_startup_with_a_clear_message(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sazon.db"
    _old_database(path)
    with pytest.raises(StaleSchemaError, match="out of date"):
        await prepare_database(_url(path), reset_stale_sqlite=False)
    assert path.exists()  # untouched


@pytest.mark.anyio
async def test_an_up_to_date_database_is_left_alone(tmp_path: Path) -> None:
    path = tmp_path / "sazon.db"
    engine = await prepare_database(_url(path), reset_stale_sqlite=True)
    await engine.dispose()
    engine = await prepare_database(_url(path), reset_stale_sqlite=True)
    await engine.dispose()
    assert not list(tmp_path.glob("*.bak-*"))
