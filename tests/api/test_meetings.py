from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_advisor_port
from app.domain.advisor.entities import (
    AdviceFeedback,
    MeetingPrep,
    MeetingType,
    Persona,
    TalkingPoint,
)
from app.domain.advisor.port import AdvisorError, MeetingContext
from tests.api.helpers import create_team


class FakeMeetingAdvisor:
    def __init__(self) -> None:
        self.contexts: list[MeetingContext] = []
        self.guidance: list[str | None] = []

    async def prepare_meeting(
        self,
        context: MeetingContext,
        *,
        meeting: MeetingType,
        guidance: str | None = None,
    ) -> MeetingPrep:
        self.contexts.append(context)
        self.guidance.append(guidance)
        return MeetingPrep(
            meeting=meeting,
            generated_at=datetime(2026, 7, 12, tzinfo=UTC),
            headline="Nothing is stuck.",
            talking_points=(
                TalkingPoint(
                    point="WIP is healthy",
                    detail="4 items in progress against 12 completed in 30d.",
                    evidence=("wip=4", "completed=12"),
                    needs_decision=False,
                ),
            ),
        )

    async def reflect(
        self,
        *,
        persona: Persona,
        feedback: Sequence[AdviceFeedback],
        current_guidance: str | None,
    ) -> str:
        return "Lead with stuck items."


async def test_prep_409_when_unconfigured(
    client: AsyncClient, settings_env: Callable[..., None]
) -> None:
    settings_env(openrouter_api_key="")
    response = await client.get(
        f"/api/meetings/prep?team_id={uuid4()}&meeting=daily_standup"
    )
    assert response.status_code == 409


async def test_prep_requires_exactly_one_scope(
    client: AsyncClient, test_app: FastAPI
) -> None:
    test_app.dependency_overrides[get_advisor_port] = lambda: FakeMeetingAdvisor()
    response = await client.get("/api/meetings/prep?meeting=daily_standup")
    assert response.status_code == 422


async def test_prep_unknown_meeting_is_422(client: AsyncClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_advisor_port] = lambda: FakeMeetingAdvisor()
    team_id = await create_team(client)
    response = await client.get(f"/api/meetings/prep?team_id={team_id}&meeting=all_hands")
    assert response.status_code == 422


async def test_prep_unknown_team_is_404_without_llm_call(
    client: AsyncClient, test_app: FastAPI
) -> None:
    fake = FakeMeetingAdvisor()
    test_app.dependency_overrides[get_advisor_port] = lambda: fake
    response = await client.get(
        f"/api/meetings/prep?team_id={uuid4()}&meeting=daily_standup"
    )
    assert response.status_code == 404
    assert fake.contexts == []  # an unknown scope must not trigger a paid LLM call


async def test_prep_happy_path(client: AsyncClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_advisor_port] = lambda: FakeMeetingAdvisor()
    team_id = await create_team(client)

    response = await client.get(
        f"/api/meetings/prep?team_id={team_id}&meeting=daily_standup"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meeting"] == "daily_standup"
    assert body["headline"] == "Nothing is stuck."
    assert body["talking_points"][0]["point"] == "WIP is healthy"
    assert body["talking_points"][0]["evidence"] == ["wip=4", "completed=12"]
    assert body["talking_points"][0]["needs_decision"] is False


async def test_prep_forwards_planning_what_ifs_to_the_forecast(
    client: AsyncClient, test_app: FastAPI
) -> None:
    fake = FakeMeetingAdvisor()
    test_app.dependency_overrides[get_advisor_port] = lambda: fake
    team_id = await create_team(client)

    response = await client.get(
        f"/api/meetings/prep?team_id={team_id}&meeting=planning"
        "&remaining=8&target_date=2026-08-01"
    )

    assert response.status_code == 200
    (context,) = fake.contexts
    assert context.delivery.forecast.remaining == 8


async def test_prep_forwards_meeting_persona_guidance(
    client: AsyncClient, test_app: FastAPI
) -> None:
    fake = FakeMeetingAdvisor()
    test_app.dependency_overrides[get_advisor_port] = lambda: fake
    team_id = await create_team(client)
    await client.post(
        "/api/personas/daily_standup/feedback",
        json={"rating": "up", "comment": None, "advice_summary": "good prep"},
    )
    reflected = await client.post("/api/personas/daily_standup/reflect")
    assert reflected.status_code == 201

    response = await client.get(
        f"/api/meetings/prep?team_id={team_id}&meeting=daily_standup"
    )

    assert response.status_code == 200
    assert fake.guidance == ["Lead with stuck items."]


async def test_prep_502_when_advisor_fails(client: AsyncClient, test_app: FastAPI) -> None:
    class FailingAdvisor:
        async def prepare_meeting(
            self,
            context: MeetingContext,
            *,
            meeting: MeetingType,
            guidance: str | None = None,
        ) -> MeetingPrep:
            raise AdvisorError("OpenRouter request failed")

    test_app.dependency_overrides[get_advisor_port] = lambda: FailingAdvisor()
    team_id = await create_team(client)

    response = await client.get(
        f"/api/meetings/prep?team_id={team_id}&meeting=retrospective"
    )

    assert response.status_code == 502
    assert "OpenRouter request failed" in response.json()["detail"]
