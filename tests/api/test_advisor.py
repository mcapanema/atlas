import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_advisor_port
from app.domain.advisor.entities import DeliveryAdvice, Persona, Recommendation
from app.domain.advisor.port import AdvisorError, DeliveryContext
from tests.api.helpers import create_team, settle


class FakeAdvisor:
    def __init__(self) -> None:
        self.personas: list[Persona] = []
        self.gate: asyncio.Event | None = None

    async def advise(
        self,
        context: DeliveryContext,
        *,
        persona: Persona = Persona.AGILE_COACH,
        guidance: str | None = None,
    ) -> DeliveryAdvice:
        self.personas.append(persona)
        if self.gate is not None:
            await self.gate.wait()
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


async def test_post_returns_202_running_then_get_returns_succeeded(
    rules_client: AsyncClient, rules_app: FastAPI
) -> None:
    fake = FakeAdvisor()
    fake.gate = asyncio.Event()
    rules_app.dependency_overrides[get_advisor_port] = lambda: fake
    team_id = await create_team(rules_client)

    posted = await rules_client.post(f"/api/recommendations?team_id={team_id}")

    assert posted.status_code == 202
    assert posted.json()["status"] == "running"
    assert posted.json()["advice"] is None
    running = await rules_client.get(f"/api/recommendations?team_id={team_id}")
    assert running.json()["id"] == posted.json()["id"]
    assert running.json()["status"] == "running"

    fake.gate.set()
    await settle(rules_app)

    body = (await rules_client.get(f"/api/recommendations?team_id={team_id}")).json()
    assert body["id"] == posted.json()["id"]
    assert body["status"] == "succeeded"
    assert body["finished_at"] is not None
    assert body["advice"]["summary"] == "Flow is healthy."
    assert body["advice"]["recommendations"][0]["title"] == "Lower WIP"
    assert body["advice"]["recommendations"][0]["evidence"] == ["wip=12", "completed=3"]


async def test_get_without_any_run_returns_null(
    rules_client: AsyncClient, rules_app: FastAPI
) -> None:
    team_id = await create_team(rules_client)

    response = await rules_client.get(f"/api/recommendations?team_id={team_id}")

    assert response.status_code == 200
    assert response.json() is None


async def test_post_twice_while_running_calls_the_advisor_once(
    rules_client: AsyncClient, rules_app: FastAPI
) -> None:
    fake = FakeAdvisor()
    fake.gate = asyncio.Event()
    rules_app.dependency_overrides[get_advisor_port] = lambda: fake
    team_id = await create_team(rules_client)

    first = await rules_client.post(f"/api/recommendations?team_id={team_id}")
    second = await rules_client.post(f"/api/recommendations?team_id={team_id}")
    fake.gate.set()
    await settle(rules_app)

    assert second.json()["id"] == first.json()["id"]
    assert fake.personas == [Persona.AGILE_COACH]


async def test_get_reads_stored_advice_without_a_key(
    rules_client: AsyncClient, rules_app: FastAPI, settings_env: Callable[..., None]
) -> None:
    rules_app.dependency_overrides[get_advisor_port] = lambda: FakeAdvisor()
    team_id = await create_team(rules_client)
    await rules_client.post(f"/api/recommendations?team_id={team_id}")
    await settle(rules_app)
    rules_app.dependency_overrides.clear()

    settings_env(openrouter_api_key="")

    got = await rules_client.get(f"/api/recommendations?team_id={team_id}")
    posted = await rules_client.post(f"/api/recommendations?team_id={team_id}")
    assert got.status_code == 200
    assert got.json()["advice"]["summary"] == "Flow is healthy."
    assert posted.status_code == 409


async def test_post_409_when_unconfigured(
    client: AsyncClient, settings_env: Callable[..., None]
) -> None:
    settings_env(openrouter_api_key="")
    response = await client.post(f"/api/recommendations?team_id={uuid4()}")
    assert response.status_code == 409


async def test_post_unconfigured_beats_unknown_scope(
    rules_client: AsyncClient, settings_env: Callable[..., None]
) -> None:
    settings_env(openrouter_api_key="")
    response = await rules_client.post(f"/api/recommendations?team_id={uuid4()}")
    assert response.status_code == 409


async def test_requires_exactly_one_scope(client: AsyncClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_advisor_port] = lambda: FakeAdvisor()
    assert (await client.post("/api/recommendations")).status_code == 422
    assert (await client.get("/api/recommendations")).status_code == 422


async def test_post_unknown_team_writes_no_run(
    rules_client: AsyncClient, rules_app: FastAPI
) -> None:
    fake = FakeAdvisor()
    rules_app.dependency_overrides[get_advisor_port] = lambda: fake
    unknown = uuid4()

    response = await rules_client.post(f"/api/recommendations?team_id={unknown}")

    assert response.status_code == 404
    await settle(rules_app)
    assert fake.personas == []  # an unknown scope must not trigger a paid LLM call
    assert (await rules_client.get(f"/api/recommendations?team_id={unknown}")).status_code == 404


async def test_failed_run_reports_the_error(rules_client: AsyncClient, rules_app: FastAPI) -> None:
    class FailingAdvisor:
        async def advise(
            self,
            context: DeliveryContext,
            *,
            persona: Persona = Persona.AGILE_COACH,
            guidance: str | None = None,
        ) -> DeliveryAdvice:
            raise AdvisorError("OpenRouter request failed")

    rules_app.dependency_overrides[get_advisor_port] = lambda: FailingAdvisor()
    team_id = await create_team(rules_client)

    posted = await rules_client.post(f"/api/recommendations?team_id={team_id}")
    await settle(rules_app)

    assert posted.status_code == 202
    body = (await rules_client.get(f"/api/recommendations?team_id={team_id}")).json()
    assert body["status"] == "failed"
    assert "OpenRouter request failed" in body["error"]
    assert body["advice"] is None


async def test_persona_and_window_select_the_run(
    rules_client: AsyncClient, rules_app: FastAPI
) -> None:
    fake = FakeAdvisor()
    rules_app.dependency_overrides[get_advisor_port] = lambda: fake
    team_id = await create_team(rules_client)

    default = await rules_client.post(f"/api/recommendations?team_id={team_id}")
    analyst = await rules_client.post(
        f"/api/recommendations?team_id={team_id}&persona=delivery_analyst"
    )
    wide = await rules_client.post(f"/api/recommendations?team_id={team_id}&window_days=90")
    await settle(rules_app)

    assert len({r.json()["id"] for r in (default, analyst, wide)}) == 3
    assert sorted(fake.personas) == sorted(
        [Persona.AGILE_COACH, Persona.AGILE_COACH, Persona.DELIVERY_ANALYST]
    )
    for query, run in (
        ("", default),
        ("&persona=delivery_analyst", analyst),
        ("&window_days=90", wide),
    ):
        got = await rules_client.get(f"/api/recommendations?team_id={team_id}{query}")
        assert got.json()["id"] == run.json()["id"]
    other = await rules_client.get(f"/api/recommendations?team_id={team_id}&window_days=60")
    assert other.json() is None


async def test_unknown_persona_is_422(client: AsyncClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_advisor_port] = lambda: FakeAdvisor()
    team_id = await create_team(client)

    response = await client.post(f"/api/recommendations?team_id={team_id}&persona=fortune_teller")

    assert response.status_code == 422
