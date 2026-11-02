from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import app.infrastructure.repositories  # noqa: F401  # registers ORM models on Base.metadata
from app.config import get_settings
from app.domain.auth.passwords import hash_password
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import enable_sqlite_pragmas
from app.main import create_app

ADMIN_EMAIL = "admin@atlas.test"
ADMIN_PASSWORD = "correct-horse-battery"
# scrypt is slow on purpose: hash once per test session, not once per test.
PASSWORD_HASH = hash_password(ADMIN_PASSWORD)


@pytest_asyncio.fixture
async def sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # StaticPool keeps a single in-memory connection alive so schema persists across sessions.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    enable_sqlite_pragmas(engine)  # tests run under production FK semantics
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as session:
        yield session


@pytest_asyncio.fixture
async def test_app(sessionmaker: async_sessionmaker[AsyncSession]) -> FastAPI:
    application = create_app()
    application.state.sessionmaker = sessionmaker  # in-memory test DB
    return application


async def _signed_in_client(
    app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> AsyncClient:
    # Imported here: helpers imports this module for PASSWORD_HASH.
    from tests.api.helpers import sign_in

    _, token = await sign_in(sessionmaker, email=ADMIN_EMAIL, is_admin=True)
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://localhost",
        cookies={"atlas_session": token},
    )


@pytest_asyncio.fixture
async def client(
    test_app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[AsyncClient]:
    """Signed in as the admin ADMIN_EMAIL."""
    async with await _signed_in_client(test_app, sessionmaker) as http_client:
        yield http_client


@pytest_asyncio.fixture
async def anon_client(test_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Not signed in: no session cookie."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as http_client:
        yield http_client


@pytest_asyncio.fixture
async def file_sessionmaker(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A file-backed DB with a real connection pool.

    For code that opens concurrent sessions (the metric-rules recompute
    runner): the single shared in-memory connection above can't isolate
    their transactions.
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'atlas.db'}")
    enable_sqlite_pragmas(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def rules_app(
    file_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[FastAPI]:
    """The app on the file-backed DB; stops the advice, sync and recompute runners on teardown."""
    application = create_app()
    application.state.sessionmaker = file_sessionmaker
    yield application
    jobs = getattr(application.state, "sync_job_runner", None)
    if jobs is not None:
        await jobs.close()
    advice = getattr(application.state, "advice_runner", None)
    if advice is not None:
        await advice.close()
    runner = getattr(application.state, "recompute_runner", None)
    if runner is not None:
        await runner.close()


@pytest_asyncio.fixture
async def rules_client(
    rules_app: FastAPI, file_sessionmaker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[AsyncClient]:
    """Signed in as the admin ADMIN_EMAIL."""
    async with await _signed_in_client(rules_app, file_sessionmaker) as http_client:
        yield http_client


@pytest.fixture(autouse=True)
def _secret_key_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the credential key file at a temp dir so no test writes ``data/atlas.key``."""
    monkeypatch.setenv("ATLAS_SECRET_KEY_FILE", str(tmp_path / "atlas.key"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    """The one way tests override settings.

    Sets ``ATLAS_<FIELD>`` env vars and clears the ``get_settings`` cache
    (cleared again on teardown so later tests re-read a clean environment).
    Exercises the real Settings loading path — and because a real env var
    always beats ``.env``, passing ``""`` unsets a setting hermetically even
    when the developer's ``.env`` sets it. Don't ``monkeypatch.setattr``
    ``get_settings`` at import sites; that bypasses the cache and breaks
    silently when imports move.
    """

    def _set(**overrides: str) -> None:
        for field, value in overrides.items():
            monkeypatch.setenv(f"ATLAS_{field.upper()}", value)
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()
