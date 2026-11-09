import asyncio
import logging
import shutil
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text

from app.infrastructure.database.session import build_sessionmaker, set_sqlite_journal_mode


def _header_mode(db: Path) -> int:
    """Byte 18 of the SQLite header: 1 = rollback journal, 2 = WAL."""
    return db.read_bytes()[18]


def _wal_database(db: Path) -> None:
    raw = sqlite3.connect(db)
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("CREATE TABLE t (x INTEGER)")
    raw.commit()
    raw.close()


async def test_build_sessionmaker_enables_fk_enforcement_and_wal(tmp_path: Path) -> None:
    sessionmaker = build_sessionmaker(f"sqlite+aiosqlite:///{tmp_path / 'pragmas.db'}")
    async with sessionmaker() as session:
        assert (await session.execute(text("PRAGMA foreign_keys"))).scalar() == 1
        assert (await session.execute(text("PRAGMA journal_mode"))).scalar() == "wal"
    await sessionmaker.kw["bind"].dispose()


async def test_delete_mode_converts_an_existing_wal_database(tmp_path: Path) -> None:
    # A WAL database whose rows still live only in its -wal file: copied while
    # the writer is open, the way a crashed container or make dev leaves it.
    live, db = tmp_path / "live.db", tmp_path / "shared.db"
    raw = sqlite3.connect(live)
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("PRAGMA wal_autocheckpoint=0")
    raw.execute("CREATE TABLE t (x INTEGER)")
    raw.executemany("INSERT INTO t VALUES (?)", [(1,), (2,), (3,)])
    raw.commit()
    for suffix in ("", "-wal", "-shm"):
        shutil.copyfile(f"{live}{suffix}", f"{db}{suffix}")
    raw.close()

    sessionmaker = build_sessionmaker(f"sqlite+aiosqlite:///{db}", journal_mode="delete")
    async with sessionmaker() as session:
        assert (await session.execute(text("SELECT count(*) FROM t"))).scalar() == 3
        # A WAL connection keeps its -wal file while open; a converted one has none.
        assert not (tmp_path / "shared.db-wal").exists()
        assert (await session.execute(text("PRAGMA journal_mode"))).scalar() == "delete"
    await sessionmaker.kw["bind"].dispose()


async def test_delete_mode_reader_is_not_blocked_by_an_open_writer(tmp_path: Path) -> None:
    sessionmaker = build_sessionmaker(
        f"sqlite+aiosqlite:///{tmp_path / 'rw.db'}", journal_mode="delete"
    )
    async with sessionmaker() as setup:
        await setup.execute(text("CREATE TABLE t (x INTEGER)"))
        await setup.execute(text("INSERT INTO t VALUES (1)"))
        await setup.commit()

    async with sessionmaker() as writer, sessionmaker() as reader:
        await writer.execute(text("INSERT INTO t VALUES (2)"))  # uncommitted: RESERVED lock
        assert (await reader.execute(text("SELECT count(*) FROM t"))).scalar() == 1
        await writer.rollback()
    await sessionmaker.kw["bind"].dispose()


async def test_delete_mode_reader_survives_a_writer_that_outgrows_the_cache(
    tmp_path: Path,
) -> None:
    # A big sync spills dirty pages past the page cache, which in rollback-journal
    # mode escalates the writer to EXCLUSIVE and locks every reader out until commit.
    sessionmaker = build_sessionmaker(
        f"sqlite+aiosqlite:///{tmp_path / 'spill.db'}", journal_mode="delete"
    )
    async with sessionmaker() as setup:
        await setup.execute(text("CREATE TABLE t (x BLOB)"))
        await setup.commit()

    async with sessionmaker() as writer, sessionmaker() as reader:
        await writer.execute(text("PRAGMA cache_size=10"))  # 10 pages: forces the spill
        await writer.execute(
            text(
                "INSERT INTO t SELECT randomblob(1000) FROM (WITH RECURSIVE n(i) AS"
                " (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 2000) SELECT i FROM n)"
            )
        )
        assert (await reader.execute(text("SELECT count(*) FROM t"))).scalar() == 0
        await writer.rollback()
    await sessionmaker.kw["bind"].dispose()


async def test_build_sessionmaker_converts_before_any_connection_opens(tmp_path: Path) -> None:
    db = tmp_path / "shared.db"
    _wal_database(db)
    sessionmaker = build_sessionmaker(f"sqlite+aiosqlite:///{db}", journal_mode="delete")
    assert _header_mode(db) == 1
    await sessionmaker.kw["bind"].dispose()


async def test_build_sessionmaker_creates_a_missing_database_in_the_requested_mode(
    tmp_path: Path,
) -> None:
    db = tmp_path / "fresh.db"
    sessionmaker = build_sessionmaker(f"sqlite+aiosqlite:///{db}", journal_mode="wal")
    async with sessionmaker() as session:
        assert (await session.execute(text("PRAGMA journal_mode"))).scalar() == "wal"
    await sessionmaker.kw["bind"].dispose()


def test_build_sessionmaker_fails_when_another_connection_blocks_the_switch(
    tmp_path: Path,
) -> None:
    db = tmp_path / "busy.db"
    _wal_database(db)
    holder = sqlite3.connect(db)
    holder.execute("SELECT count(*) FROM t").fetchall()  # a WAL connection holds SHARED while open
    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            build_sessionmaker(f"sqlite+aiosqlite:///{db}", journal_mode="delete")
    finally:
        holder.close()


def test_set_sqlite_journal_mode_ignores_non_file_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # a relative-path bug would create a file here
    set_sqlite_journal_mode("postgresql+asyncpg://atlas@localhost/atlas", "delete")
    set_sqlite_journal_mode("sqlite+aiosqlite:///:memory:", "delete")
    set_sqlite_journal_mode("sqlite+aiosqlite://", "delete")
    assert list(tmp_path.iterdir()) == []


async def test_new_connections_survive_a_wal_switch_behind_the_pool(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # The 2026-11-09 incident: the file went to WAL while the pool held a
    # connection, and every new pooled connection failed to leave WAL.
    db = tmp_path / "flipped.db"
    sessionmaker = build_sessionmaker(f"sqlite+aiosqlite:///{db}", journal_mode="delete")
    async with sessionmaker() as setup:
        await setup.execute(text("CREATE TABLE t (x INTEGER)"))
        await setup.commit()

    async with sessionmaker() as held:
        await held.execute(text("SELECT 1"))
        outside = sqlite3.connect(db)
        outside.execute("PRAGMA journal_mode=WAL")
        outside.close()
        await held.execute(text("SELECT count(*) FROM t"))  # held now has the file open as WAL

        async def count() -> int | None:
            async with sessionmaker() as session:
                return (await session.execute(text("SELECT count(*) FROM t"))).scalar()

        with caplog.at_level(logging.WARNING, logger="app.infrastructure.database.session"):
            assert await asyncio.gather(*(count() for _ in range(4))) == [0, 0, 0, 0]
    assert "wal" in caplog.text
    assert "delete" in caplog.text
    await sessionmaker.kw["bind"].dispose()
