from collections.abc import AsyncIterator

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
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import enable_sqlite_pragmas
from app.main import create_app


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


@pytest_asyncio.fixture
async def client(test_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
