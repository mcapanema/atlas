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
from app.domain.metrics.windows import STATS_WINDOW_DAYS
from tests.api.helpers import create_org_and_team, create_team, settle


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
    response = await client.post(f"/api/meetings/prep?team_id={uuid4()}&meeting=daily_standup")
    assert response.status_code == 409


async def test_prep_requires_exactly_one_scope(client: AsyncClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_advisor_port] = lambda: FakeMeetingAdvisor()
    assert (await client.post("/api/meetings/prep?meeting=daily_standup")).status_code == 422
    assert (await client.get("/api/meetings/prep?meeting=daily_standup")).status_code == 422


async def test_prep_unknown_meeting_is_422(client: AsyncClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_advisor_port] = lambda: FakeMeetingAdvisor()
    team_id = await create_team(client)
    response = await client.post(f"/api/meetings/prep?team_id={team_id}&meeting=all_hands")
    assert response.status_code == 422


async def test_prep_unknown_team_is_404_without_llm_call(
    rules_client: AsyncClient, rules_app: FastAPI
) -> None:
    fake = FakeMeetingAdvisor()
    rules_app.dependency_overrides[get_advisor_port] = lambda: fake
    response = await rules_client.post(
        f"/api/meetings/prep?team_id={uuid4()}&meeting=daily_standup"
    )
    await settle(rules_app)
    assert response.status_code == 404
    assert fake.contexts == []  # an unknown scope must not trigger a paid LLM call


async def test_meeting_post_then_get(rules_client: AsyncClient, rules_app: FastAPI) -> None:
    rules_app.dependency_overrides[get_advisor_port] = lambda: FakeMeetingAdvisor()
    team_id = await create_team(rules_client)
    url = f"/api/meetings/prep?team_id={team_id}&meeting=daily_standup"
    assert (await rules_client.get(url)).json() is None

    posted = await rules_client.post(url)
    await settle(rules_app)

    assert posted.status_code == 202
    assert posted.json()["status"] == "running"
    assert posted.json()["prep"] is None
    body = (await rules_client.get(url)).json()
    assert body["id"] == posted.json()["id"]
    assert body["status"] == "succeeded"
    assert body["prep"]["meeting"] == "daily_standup"
    assert body["prep"]["headline"] == "Nothing is stuck."
    assert body["prep"]["talking_points"][0]["point"] == "WIP is healthy"
    assert body["prep"]["talking_points"][0]["evidence"] == ["wip=4", "completed=12"]
    assert body["prep"]["talking_points"][0]["needs_decision"] is False


async def test_meeting_params_are_part_of_the_key(
    rules_client: AsyncClient, rules_app: FastAPI
) -> None:
    fake = FakeMeetingAdvisor()
    rules_app.dependency_overrides[get_advisor_port] = lambda: fake
    team_id = await create_team(rules_client)
    base = f"/api/meetings/prep?team_id={team_id}&meeting=planning"

    plain = await rules_client.post(base)
    what_if = await rules_client.post(f"{base}&remaining=5&target_date=2026-08-01")
    await settle(rules_app)

    assert plain.json()["id"] != what_if.json()["id"]
    assert (await rules_client.get(base)).json()["id"] == plain.json()["id"]
    got = await rules_client.get(f"{base}&remaining=5&target_date=2026-08-01")
    assert got.json()["id"] == what_if.json()["id"]
    assert (await rules_client.get(f"{base}&remaining=6")).json() is None
    forecasts = sorted(c.delivery.forecast.remaining for c in fake.contexts)
    assert len(forecasts) == 2
    assert forecasts[-1] == 5


async def test_prep_forwards_meeting_persona_guidance(
    rules_client: AsyncClient, rules_app: FastAPI
) -> None:
    fake = FakeMeetingAdvisor()
    rules_app.dependency_overrides[get_advisor_port] = lambda: fake
    team_id = await create_team(rules_client)
    await rules_client.post(
        "/api/personas/daily_standup/feedback",
        json={"rating": "up", "comment": None, "advice_summary": "good prep"},
    )
    reflected = await rules_client.post("/api/personas/daily_standup/reflect")
    assert reflected.status_code == 201

    response = await rules_client.post(
        f"/api/meetings/prep?team_id={team_id}&meeting=daily_standup"
    )
    await settle(rules_app)

    assert response.status_code == 202
    assert fake.guidance == ["Lead with stuck items."]


async def test_prep_failure_is_stored_on_the_run(
    rules_client: AsyncClient, rules_app: FastAPI
) -> None:
    class FailingAdvisor:
        async def prepare_meeting(
            self,
            context: MeetingContext,
            *,
            meeting: MeetingType,
            guidance: str | None = None,
        ) -> MeetingPrep:
            raise AdvisorError("OpenRouter request failed")

    rules_app.dependency_overrides[get_advisor_port] = lambda: FailingAdvisor()
    team_id = await create_team(rules_client)
    url = f"/api/meetings/prep?team_id={team_id}&meeting=retrospective"

    assert (await rules_client.post(url)).status_code == 202
    await settle(rules_app)

    body = (await rules_client.get(url)).json()
    assert body["status"] == "failed"
    assert "OpenRouter request failed" in body["error"]
    assert body["prep"] is None


async def test_retrospective_default_window_uses_sprint_length(
    rules_app: FastAPI, rules_client: AsyncClient
) -> None:
    fake = FakeMeetingAdvisor()
    rules_app.dependency_overrides[get_advisor_port] = lambda: fake
    _, team = await create_org_and_team(rules_client)
    await rules_client.patch(f"/api/teams/{team}/metric-rules", json={"sprint_length_days": 10})
    await settle(rules_app)

    all_params: list[dict[str, str | int]] = [
        {"meeting": "retrospective"},
        {"meeting": "retrospective", "window_days": 21},
        {"meeting": "daily_standup"},
    ]
    for params in all_params:
        response = await rules_client.post("/api/meetings/prep", params={"team_id": team, **params})
        assert response.status_code == 202
        await settle(rules_app)

    spans = [
        (c.delivery.flow.window_end - c.delivery.flow.window_start).days for c in fake.contexts
    ]
    assert spans == [10, 21, STATS_WINDOW_DAYS]
    got = await rules_client.get(
        "/api/meetings/prep", params={"team_id": team, "meeting": "retrospective"}
    )
    assert got.json()["status"] == "succeeded"
