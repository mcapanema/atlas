from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def enable_sqlite_pragmas(engine: AsyncEngine) -> None:
    """Enforce FKs and use WAL on every SQLite connection; no-op elsewhere.

    SQLite ships with foreign_keys OFF per connection — without this, the
    schema's FK constraints are decorative. WAL lets readers coexist with a
    writer. Postgres needs neither, hence the dialect guard.
    """
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def build_sessionmaker(database_url: str, echo: bool = False) -> async_sessionmaker[AsyncSession]:
    """Build an async session factory bound to a fresh engine for ``database_url``."""
    engine = create_async_engine(database_url, echo=echo)
    enable_sqlite_pragmas(engine)
    return async_sessionmaker(engine, expire_on_commit=False)
