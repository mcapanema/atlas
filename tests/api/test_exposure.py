"""Who may reach what (ADR-0012): UI/API local-only, the MCP mount remote."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.responses import PlainTextResponse
from starlette.types import Receive, Scope, Send

from app.api.exposure import LocalOnlyMiddleware

_TUNNEL = {"host": "abc.trycloudflare.com", "x-forwarded-for": "203.0.113.1"}


async def _ok(scope: Scope, receive: Receive, send: Send) -> None:
    await PlainTextResponse("ok")(scope, receive, send)


def _client(public_prefix: str | None = "/mcp/secret-token") -> AsyncClient:
    app = LocalOnlyMiddleware(_ok, public_prefix=public_prefix)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost")


@pytest.mark.parametrize(
    # Docker's port map, Vite's dev proxy, plain loopback, IPv6 loopback.
    "host",
    [
        "localhost",
        "localhost:8000",
        "localhost:5173",
        "127.0.0.1:8000",
        "[::1]:8000",
        "0.0.0.0:8000",
    ],
)
async def test_loopback_requests_reach_the_app(host: str) -> None:
    async with _client() as client:
        response = await client.get("/api/teams", headers={"host": host})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        "attacker.example",  # DNS rebinding
        "192.168.1.20:8000",  # a LAN client
        "abc.trycloudflare.com",  # a Host-preserving tunnel
        "localhost.attacker.example",
    ],
)
async def test_non_loopback_hosts_are_refused(host: str) -> None:
    async with _client() as client:
        response = await client.get("/api/teams", headers={"host": host})

    assert response.status_code == 403


@pytest.mark.parametrize(
    "header", ["forwarded", "x-forwarded-for", "x-forwarded-host", "x-real-ip", "cf-connecting-ip"]
)
async def test_proxied_requests_are_refused_even_under_a_loopback_host(header: str) -> None:
    async with _client() as client:
        response = await client.get(
            "/api/teams", headers={"host": "localhost:8000", header: "203.0.113.1"}
        )

    assert response.status_code == 403


async def test_only_the_mcp_mount_answers_through_a_tunnel() -> None:
    async with _client() as client:
        mount = await client.post("/mcp/secret-token", headers=_TUNNEL)
        inside = await client.post("/mcp/secret-token/", headers=_TUNNEL)
        lookalike = await client.post("/mcp/secret-token-longer/", headers=_TUNNEL)
        other = await client.get("/", headers=_TUNNEL)

    assert (mount.status_code, inside.status_code) == (200, 200)
    assert (lookalike.status_code, other.status_code) == (403, 403)


async def test_without_a_token_nothing_is_public() -> None:
    async with _client(public_prefix=None) as client:
        response = await client.post("/mcp/anything/", headers=_TUNNEL)

    assert response.status_code == 403


async def test_the_app_refuses_tunneled_requests_to_its_api_docs(test_app: FastAPI) -> None:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        tunneled = await client.get("/docs", headers=_TUNNEL)
        local = await client.get("/docs")

    assert (tunneled.status_code, local.status_code) == (403, 200)
