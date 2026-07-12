from collections.abc import Callable

from httpx import AsyncClient

from tests.api.helpers import create_team


async def test_context_returns_digest_without_openrouter_key(
    client: AsyncClient, settings_env: Callable[..., None]
) -> None:
    # The digest is computed metrics only — no LLM, so no key required.
    settings_env(openrouter_api_key="")
    team_id = await create_team(client)

    response = await client.get("/api/recommendations/context", params={"team_id": team_id})

    assert response.status_code == 200
    text = response.json()["context"]
    assert "Flow metrics" in text
    assert "Monte Carlo forecast" in text


async def test_context_requires_exactly_one_scope(client: AsyncClient) -> None:
    response = await client.get("/api/recommendations/context")

    assert response.status_code == 422
    assert "exactly one" in response.json()["detail"]
