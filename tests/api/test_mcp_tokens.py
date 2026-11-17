"""Each signed-in user issues, lists and revokes their own MCP tokens."""

from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.api.helpers import sign_in


async def test_create_shows_the_token_once_and_list_never_does(client: AsyncClient) -> None:
    created = await client.post(
        "/api/mcp-tokens", json={"name": "Claude Code", "access": "read_write"}
    )

    assert created.status_code == 201
    body = created.json()
    assert body["token"].startswith("atlas_mcp_")
    assert body["hint"] == body["token"][-4:]
    assert body["access"] == "read_write"
    listed = (await client.get("/api/mcp-tokens")).json()
    assert [t["name"] for t in listed] == ["Claude Code"]
    assert "token" not in listed[0]
    assert "token_hash" not in listed[0]


async def test_access_defaults_to_read(client: AsyncClient) -> None:
    created = await client.post("/api/mcp-tokens", json={"name": "x"})

    assert created.status_code == 201
    assert created.json()["access"] == "read"


async def test_a_blank_name_or_unknown_access_is_422(client: AsyncClient) -> None:
    assert (await client.post("/api/mcp-tokens", json={"name": ""})).status_code == 422
    unknown = await client.post("/api/mcp-tokens", json={"name": "x", "access": "admin"})
    assert unknown.status_code == 422
    extra = await client.post("/api/mcp-tokens", json={"name": "x", "user_id": str(uuid4())})
    assert extra.status_code == 422


async def test_a_user_sees_and_revokes_only_their_own_tokens(
    client: AsyncClient,
    anon_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    token_id = (await client.post("/api/mcp-tokens", json={"name": "mine"})).json()["id"]
    _, session_token = await sign_in(sessionmaker, email="bob@atlas.test")
    headers = {"Cookie": f"atlas_session={session_token}"}

    assert (await anon_client.get("/api/mcp-tokens", headers=headers)).json() == []
    other = await anon_client.delete(f"/api/mcp-tokens/{token_id}", headers=headers)
    assert other.status_code == 404
    assert len((await client.get("/api/mcp-tokens")).json()) == 1


async def test_revoke_answers_204_then_the_list_is_empty(client: AsyncClient) -> None:
    token_id = (await client.post("/api/mcp-tokens", json={"name": "x"})).json()["id"]

    assert (await client.delete(f"/api/mcp-tokens/{token_id}")).status_code == 204
    assert (await client.get("/api/mcp-tokens")).json() == []
    assert (await client.delete(f"/api/mcp-tokens/{token_id}")).status_code == 404
