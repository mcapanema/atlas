import shutil
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
