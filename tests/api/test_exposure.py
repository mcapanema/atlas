"""Who may reach what (ADR-0012): UI/API local-only, the MCP mount remote."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.responses import PlainTextResponse
from starlette.types import Message, Receive, Scope, Send
from starlette.websockets import WebSocket

from app.api.exposure import LocalOnlyMiddleware, is_local

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


@pytest.mark.parametrize(
    ("headers", "local"),
    [
        ([(b"host", b"LOCALHOST:8000")], True),  # Host is case-insensitive
        ([(b"host", b"[::1]:8000")], True),
        ([], False),  # no Host at all
        ([(b"host", b"")], False),
        ([(b"host", b"[::1]evil")], False),  # junk after the IPv6 literal
        ([(b"host", b"[localhost]")], False),  # brackets are for IPv6 only
        ([(b"host", b"[127.0.0.1]:8000")], False),
        ([(b"host", b"::1")], False),  # an IPv6 Host must be bracketed
        ([(b"host", b"attacker.example"), (b"host", b"localhost")], False),
        ([(b"host", b"localhost"), (b"host", b"localhost")], False),  # duplicates fail closed
    ],
)
def test_is_local_parses_the_host_strictly(headers: list[tuple[bytes, bytes]], local: bool) -> None:
    assert is_local({"type": "http", "headers": headers}) is local


async def _echo_websocket(scope: Scope, receive: Receive, send: Send) -> None:
    websocket = WebSocket(scope, receive, send)
    await websocket.accept()
    await websocket.send_text("ok")
    await websocket.close()


async def _drive_websocket(headers: list[tuple[bytes, bytes]]) -> list[Message]:
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "websocket.connect"}

    async def send(message: Message) -> None:
        sent.append(message)

    scope = {"type": "websocket", "path": "/ws", "headers": headers}
    await LocalOnlyMiddleware(_echo_websocket)(scope, receive, send)
    return sent


async def test_websockets_are_local_only_too() -> None:
    local = await _drive_websocket([(b"host", b"localhost")])
    assert {"type": "websocket.accept", "subprotocol": None, "headers": []} in local
    assert {"type": "websocket.send", "text": "ok"} in local

    tunnelled = await _drive_websocket(
        [(b"host", b"localhost"), (b"x-forwarded-for", b"203.0.113.1")]
    )
    assert [m["type"] for m in tunnelled] == ["websocket.close"]
    assert tunnelled[0]["code"] == 1008
