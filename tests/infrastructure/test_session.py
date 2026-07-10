from pathlib import Path

from sqlalchemy import text

from app.infrastructure.database.session import build_sessionmaker


async def test_build_sessionmaker_enables_fk_enforcement_and_wal(tmp_path: Path) -> None:
    sessionmaker = build_sessionmaker(f"sqlite+aiosqlite:///{tmp_path / 'pragmas.db'}")
    async with sessionmaker() as session:
        assert (await session.execute(text("PRAGMA foreign_keys"))).scalar() == 1
        assert (await session.execute(text("PRAGMA journal_mode"))).scalar() == "wal"
    await sessionmaker.kw["bind"].dispose()
