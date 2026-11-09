import logging
import sqlite3
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import SqliteJournalMode

logger = logging.getLogger(__name__)


def set_sqlite_journal_mode(database_url: str, journal_mode: SqliteJournalMode) -> None:
    """Switch a SQLite file to ``journal_mode`` once, before any pool exists; no-op elsewhere.

    Leaving WAL fails at once ("database is locked", no busy wait) while any
    other connection has the file open, since every WAL connection holds a
    SHARED lock. So the switch runs here, on one connection of its own, and
    never per pooled connection: there it made every new connection fail as
    soon as the file was in WAL behind a live pool (2026-11-09).
    """
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
        return
    connection = sqlite3.connect(url.database)
    try:
        mode = connection.execute(f"PRAGMA journal_mode={journal_mode}").fetchone()[0]
    finally:
        connection.close()
    if mode != journal_mode:
        raise sqlite3.OperationalError(
            f"database is locked: can't switch to {journal_mode} journal mode (still {mode})"
        )


def enable_sqlite_pragmas(engine: AsyncEngine, *, journal_mode: SqliteJournalMode = "wal") -> None:
    """Enforce FKs on every SQLite connection and report a journal-mode mismatch; no-op elsewhere.

    SQLite ships with foreign_keys OFF per connection — without this, the
    schema's FK constraints are decorative. The journal mode itself is set
    once by set_sqlite_journal_mode: WAL lets readers coexist with a writer
    on a local disk; "delete" (the rollback journal) is for filesystems where
    WAL's memory-mapped -shm file isn't reliable, such as the Docker Desktop
    bind mount in docker-compose.yml. Postgres needs neither, hence the
    dialect guard.
    """
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # Only read the mode: switching it here fails while the pool holds
        # another connection. A restart converts the file back.
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        if mode != journal_mode:
            logger.warning(
                "SQLite database is in %s journal mode, not the configured %s: another"
                " process changed it; restart Atlas to convert it back",
                mode,
                journal_mode,
            )
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
    set_sqlite_journal_mode(database_url, journal_mode)
    engine = create_async_engine(database_url, echo=echo)
    enable_sqlite_pragmas(engine, journal_mode=journal_mode)
    return async_sessionmaker(engine, expire_on_commit=False)
