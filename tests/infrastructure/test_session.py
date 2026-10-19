import sqlite3
from pathlib import Path

from sqlalchemy import text

from app.infrastructure.database.session import build_sessionmaker


async def test_build_sessionmaker_enables_fk_enforcement_and_wal(tmp_path: Path) -> None:
    sessionmaker = build_sessionmaker(f"sqlite+aiosqlite:///{tmp_path / 'pragmas.db'}")
    async with sessionmaker() as session:
        assert (await session.execute(text("PRAGMA foreign_keys"))).scalar() == 1
        assert (await session.execute(text("PRAGMA journal_mode"))).scalar() == "wal"
    await sessionmaker.kw["bind"].dispose()


async def test_delete_mode_converts_an_existing_wal_database(tmp_path: Path) -> None:
    db = tmp_path / "shared.db"
    raw = sqlite3.connect(db)
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("CREATE TABLE t (x INTEGER)")
    raw.close()

    sessionmaker = build_sessionmaker(f"sqlite+aiosqlite:///{db}", journal_mode="delete")
    async with sessionmaker() as session:
        assert (await session.execute(text("PRAGMA journal_mode"))).scalar() == "delete"
        assert (await session.execute(text("PRAGMA foreign_keys"))).scalar() == 1
    await sessionmaker.kw["bind"].dispose()

    assert not (tmp_path / "shared.db-wal").exists()


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
