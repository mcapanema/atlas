"""A write is acknowledged only once it is durable (review 2026-10-04, F1)."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.api.helpers import sign_in


async def _signed_in(app: FastAPI, sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncClient:
    _, token = await sign_in(sessionmaker)
    # raise_app_exceptions=False: observe the status a real HTTP client
    # receives, not the exception the app re-raises after responding.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(
        transport=transport, base_url="http://localhost", cookies={"atlas_session": token}
    )


async def test_a_failed_commit_is_a_5xx_not_a_success(
    test_app: FastAPI,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_commit(self: AsyncSession) -> None:
        raise RuntimeError("disk full")

    async with await _signed_in(test_app, sessionmaker) as client:
        with monkeypatch.context() as patch:
            patch.setattr(AsyncSession, "commit", failing_commit)
            response = await client.post("/api/organizations", json={"name": "Acme"})
        listed = await client.get("/api/organizations")

    assert response.status_code == 500
    assert listed.json() == []  # rolled back, and the client was told so


async def test_a_constraint_violation_at_commit_is_a_409(
    test_app: FastAPI,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def conflicting_commit(self: AsyncSession) -> None:
        raise IntegrityError("INSERT …", {}, Exception("UNIQUE constraint failed"))

    async with await _signed_in(test_app, sessionmaker) as client:
        with monkeypatch.context() as patch:
            patch.setattr(AsyncSession, "commit", conflicting_commit)
            response = await client.post("/api/organizations", json={"name": "Acme"})

    assert response.status_code == 409
