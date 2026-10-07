"""A write is acknowledged only once it is durable (review 2026-10-04, F1)."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def test_a_failed_commit_is_a_5xx_not_a_success(
    test_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_commit(self: AsyncSession) -> None:
        raise RuntimeError("disk full")

    # raise_app_exceptions=False: observe the status a real HTTP client
    # receives, not the exception the app re-raises after responding.
    transport = ASGITransport(app=test_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        with monkeypatch.context() as patch:
            patch.setattr(AsyncSession, "commit", failing_commit)
            response = await client.post("/api/organizations", json={"name": "Acme"})
        listed = await client.get("/api/organizations")

    assert response.status_code == 500
    assert listed.json() == []  # rolled back, and the client was told so


async def test_a_constraint_violation_at_commit_is_a_409(
    test_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def conflicting_commit(self: AsyncSession) -> None:
        raise IntegrityError("INSERT …", {}, Exception("UNIQUE constraint failed"))

    transport = ASGITransport(app=test_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        with monkeypatch.context() as patch:
            patch.setattr(AsyncSession, "commit", conflicting_commit)
            response = await client.post("/api/organizations", json={"name": "Acme"})

    assert response.status_code == 409
