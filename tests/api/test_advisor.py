from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_advisor_port, get_session
from app.domain.advisor.entities import DeliveryAdvice, Persona, Recommendation
from app.domain.advisor.port import AdvisorError, DeliveryContext
from tests.api.helpers import create_team


class FakeAdvisor:
    async def advise(
        self, context: DeliveryContext, *, persona: Persona = Persona.AGILE_COACH
    ) -> DeliveryAdvice:
        return DeliveryAdvice(
            generated_at=datetime(2026, 7, 10, tzinfo=UTC),
            summary="Flow is healthy.",
            recommendations=(
                Recommendation(
                    title="Lower WIP",
                    priority="high",
                    problem="WIP is 12 while weekly throughput is 3",
                    root_cause="Work is started faster than it finishes",
                    action="Set a WIP limit of 6",
                    evidence=("wip=12", "completed=3"),
                ),
            ),
        )


async def test_status_reports_unconfigured(
    client: AsyncClient, settings_env: Callable[..., None]
) -> None:
    settings_env(openrouter_api_key="")
    response = await client.get("/api/recommendations/status")
    assert response.status_code == 200
    assert response.json() == {"configured": False}


async def test_status_reports_configured(
    client: AsyncClient, settings_env: Callable[..., None]
) -> None:
    settings_env(openrouter_api_key="sk-test")
    response = await client.get("/api/recommendations/status")
    assert response.json() == {"configured": True}


async def test_recommendations_409_when_unconfigured(
    client: AsyncClient, settings_env: Callable[..., None]
) -> None:
    settings_env(openrouter_api_key="")
    response = await client.get(f"/api/recommendations?team_id={uuid4()}")
    assert response.status_code == 409


async def test_recommendations_requires_exactly_one_scope(
    client: AsyncClient, test_app: FastAPI
) -> None:
    test_app.dependency_overrides[get_advisor_port] = lambda: FakeAdvisor()
    response = await client.get("/api/recommendations")
    assert response.status_code == 422


async def test_recommendations_happy_path(client: AsyncClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_advisor_port] = lambda: FakeAdvisor()
    team_id = await create_team(client)

    response = await client.get(f"/api/recommendations?team_id={team_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Flow is healthy."
    assert body["recommendations"][0]["title"] == "Lower WIP"
    assert body["recommendations"][0]["priority"] == "high"
    assert body["recommendations"][0]["root_cause"].startswith("Work is started")
    assert body["recommendations"][0]["evidence"] == ["wip=12", "completed=3"]


async def test_transaction_released_before_llm_call(
    client: AsyncClient,
    test_app: FastAPI,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """The LLM call takes up to 120s; holding the request's DB transaction
    open for the duration blocks every other SQLite writer."""
    sessions: list[AsyncSession] = []
    in_transaction_during_advise: list[bool] = []

    async def tracking_get_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            sessions.append(session)
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    class ProbeAdvisor:
        async def advise(
            self, context: DeliveryContext, *, persona: Persona = Persona.AGILE_COACH
        ) -> DeliveryAdvice:
            in_transaction_during_advise.append(sessions[-1].in_transaction())
            return DeliveryAdvice(
                generated_at=datetime(2026, 7, 10, tzinfo=UTC),
                summary="probe",
                recommendations=(),
            )

    test_app.dependency_overrides[get_session] = tracking_get_session
    test_app.dependency_overrides[get_advisor_port] = lambda: ProbeAdvisor()
    team_id = await create_team(client)

    response = await client.get(f"/api/recommendations?team_id={team_id}")

    assert response.status_code == 200
    assert in_transaction_during_advise == [False]


async def test_recommendations_502_when_advisor_fails(
    client: AsyncClient, test_app: FastAPI
) -> None:
    class FailingAdvisor:
        async def advise(
            self, context: DeliveryContext, *, persona: Persona = Persona.AGILE_COACH
        ) -> DeliveryAdvice:
            raise AdvisorError("OpenRouter request failed")

    test_app.dependency_overrides[get_advisor_port] = lambda: FailingAdvisor()
    team_id = await create_team(client)

    response = await client.get(f"/api/recommendations?team_id={team_id}")

    assert response.status_code == 502
    assert "OpenRouter request failed" in response.json()["detail"]


async def test_recommendations_unknown_team_is_404_without_llm_call(
    client: AsyncClient, test_app: FastAPI
) -> None:
    calls: list[DeliveryContext] = []

    class RecordingAdvisor:
        async def advise(
            self, context: DeliveryContext, *, persona: Persona = Persona.AGILE_COACH
        ) -> DeliveryAdvice:
            calls.append(context)
            return DeliveryAdvice(
                generated_at=datetime(2026, 7, 10, tzinfo=UTC),
                summary="never",
                recommendations=(),
            )

    test_app.dependency_overrides[get_advisor_port] = lambda: RecordingAdvisor()

    response = await client.get(f"/api/recommendations?team_id={uuid4()}")

    assert response.status_code == 404
    assert calls == []  # an unknown scope must not trigger a paid LLM call


async def test_persona_is_forwarded_to_the_advisor(
    client: AsyncClient, test_app: FastAPI
) -> None:
    personas: list[Persona] = []

    class RecordingPersonaAdvisor:
        async def advise(
            self, context: DeliveryContext, *, persona: Persona = Persona.AGILE_COACH
        ) -> DeliveryAdvice:
            personas.append(persona)
            return DeliveryAdvice(
                generated_at=datetime(2026, 7, 10, tzinfo=UTC),
                summary="ok",
                recommendations=(),
            )

    test_app.dependency_overrides[get_advisor_port] = lambda: RecordingPersonaAdvisor()
    team_id = await create_team(client)

    response = await client.get(
        f"/api/recommendations?team_id={team_id}&persona=delivery_analyst"
    )

    assert response.status_code == 200
    assert personas == [Persona.DELIVERY_ANALYST]


async def test_unknown_persona_is_422(client: AsyncClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_advisor_port] = lambda: FakeAdvisor()
    team_id = await create_team(client)

    response = await client.get(
        f"/api/recommendations?team_id={team_id}&persona=fortune_teller"
    )

    assert response.status_code == 422
