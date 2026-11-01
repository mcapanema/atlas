from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import (
    LINEAR_NOT_CONFIGURED,
    get_advisor_port,
    get_delivery_data_source,
    github_code_source,
    linear_data_source,
)
from app.domain.credentials.entities import Credential, Integration
from app.infrastructure.ai.advisor import OpenRouterAdvisor
from app.infrastructure.connectors.github.datasource import GitHubDataSource
from app.infrastructure.connectors.linear.datasource import LinearDataSource
from tests.api.helpers import create_team, store_credential


async def test_sources_follow_the_stored_credentials(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        assert await linear_data_source(session) is None
        assert await github_code_source(session) is None
    await store_credential(sessionmaker, Credential(Integration.LINEAR, "lin"))
    await store_credential(sessionmaker, Credential(Integration.GITHUB, "ghp", owner="acme"))
    async with sessionmaker() as session:
        assert isinstance(await linear_data_source(session), LinearDataSource)
        assert isinstance(await github_code_source(session), GitHubDataSource)


async def test_dependencies_build_the_adapters_from_the_stored_credentials(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await store_credential(sessionmaker, Credential(Integration.LINEAR, "lin"))
    await store_credential(
        sessionmaker, Credential(Integration.OPENROUTER, "sk-or", model="vendor/model")
    )
    async with sessionmaker() as session:
        assert isinstance(await get_delivery_data_source(session), LinearDataSource)
        advisor = await get_advisor_port(session)
    assert isinstance(advisor, OpenRouterAdvisor)
    assert advisor._api_key == "sk-or"
    assert advisor._model == "vendor/model"


async def test_sync_without_a_stored_key_answers_409(client: AsyncClient) -> None:
    org = (await client.post("/api/organizations", json={"name": "Acme"})).json()
    response = await client.post("/api/connectors/linear/sync", json={"organization_id": org["id"]})
    assert response.status_code == 409
    assert response.json()["detail"] == LINEAR_NOT_CONFIGURED


async def test_advice_without_a_stored_key_answers_409(client: AsyncClient) -> None:
    team_id = await create_team(client)
    response = await client.post("/api/recommendations", params={"team_id": team_id})
    assert response.status_code == 409
    assert "Connectors page" in response.json()["detail"]
