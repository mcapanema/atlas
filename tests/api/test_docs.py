"""API docs are served at /api/docs behind sign-in; FastAPI's own docs are off."""

import pytest
from httpx import AsyncClient


@pytest.mark.parametrize("path", ["/api/docs", "/api/openapi.json"])
async def test_docs_need_sign_in(anon_client: AsyncClient, path: str) -> None:
    assert (await anon_client.get(path)).status_code == 401


async def test_signed_in_user_gets_the_schema(client: AsyncClient) -> None:
    schema = await client.get("/api/openapi.json")
    page = await client.get("/api/docs")

    assert schema.status_code == 200
    assert "/api/teams" in schema.json()["paths"]
    assert page.status_code == 200
    assert "/api/openapi.json" in page.text


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_framework_docs_are_off(anon_client: AsyncClient, path: str) -> None:
    response = await anon_client.get(path)

    # The SPA catch-all may answer; FastAPI's own pages must not.
    assert "swagger-ui" not in response.text
    assert "redoc" not in response.text.lower()
    assert '"openapi"' not in response.text
