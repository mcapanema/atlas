"""Every /api route outside /api/auth needs a signed-in user (ADR-0027)."""

from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import AsyncClient

from app.api.deps import require_signed_in


def test_every_api_route_outside_auth_requires_sign_in(test_app: FastAPI) -> None:
    unguarded = [
        r.path
        for r in test_app.routes
        if isinstance(r, APIRoute)
        and r.path.startswith("/api/")
        and not r.path.startswith("/api/auth/")
        and not any(d.dependency is require_signed_in for d in r.dependencies)
    ]
    assert unguarded == []


async def test_anonymous_api_call_is_401(anon_client: AsyncClient) -> None:
    response = await anon_client.get("/api/teams")

    assert response.status_code == 401
    assert response.json() == {"detail": "Sign in to use Atlas"}


async def test_health_stays_public(anon_client: AsyncClient) -> None:
    assert (await anon_client.get("/health")).status_code == 200


async def test_a_forged_internal_header_is_401(anon_client: AsyncClient) -> None:
    response = await anon_client.get("/api/teams", headers={"X-Atlas-Internal": "guess"})

    assert response.status_code == 401


async def test_an_unknown_session_cookie_is_401(anon_client: AsyncClient) -> None:
    response = await anon_client.get("/api/teams", headers={"Cookie": "atlas_session=nope"})

    assert response.status_code == 401
