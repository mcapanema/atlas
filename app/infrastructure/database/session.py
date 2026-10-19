from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import SqliteJournalMode


def enable_sqlite_pragmas(engine: AsyncEngine, *, journal_mode: SqliteJournalMode = "wal") -> None:
    """Enforce FKs and set the journal mode on every SQLite connection; no-op elsewhere.

    SQLite ships with foreign_keys OFF per connection — without this, the
    schema's FK constraints are decorative. WAL lets readers coexist with a
    writer on a local disk; "delete" (the rollback journal) is for
    filesystems where WAL's memory-mapped -shm file isn't reliable, such as
    the Docker Desktop bind mount in docker-compose.yml. Postgres needs
    neither, hence the dialect guard.
    """
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA journal_mode={journal_mode}")
        if journal_mode == "delete":
            # A writer that spills dirty pages past the cache escalates to
            # EXCLUSIVE and locks readers out until commit; keeping a big sync's
            # pages in RAM instead keeps the dashboard readable meanwhile.
            cursor.execute("PRAGMA cache_spill=OFF")
        cursor.close()


def build_sessionmaker(
    database_url: str, echo: bool = False, journal_mode: SqliteJournalMode = "wal"
) -> async_sessionmaker[AsyncSession]:
    """Build an async session factory bound to a fresh engine for ``database_url``."""
    engine = create_async_engine(database_url, echo=echo)
    enable_sqlite_pragmas(engine, journal_mode=journal_mode)
    return async_sessionmaker(engine, expire_on_commit=False)
