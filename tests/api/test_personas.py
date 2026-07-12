from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime

from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_advisor_port
from app.domain.advisor.entities import AdviceFeedback, DeliveryAdvice, Persona
from app.domain.advisor.port import DeliveryContext


class FakeReflectingAdvisor:
    """Advisor double for reflect tests; `guidance` is what reflection returns."""

    def __init__(
        self,
        guidance: str = "Lead with WIP limits.",
        on_reflect: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.guidance = guidance
        # Hook run from inside reflect(), before it returns — lets a test
        # simulate feedback arriving while the (slow) LLM call is in flight.
        self.on_reflect = on_reflect
        self.reflect_calls: list[tuple[Persona, int, str | None]] = []

    async def advise(
        self,
        context: DeliveryContext,
        *,
        persona: Persona = Persona.AGILE_COACH,
        guidance: str | None = None,
    ) -> DeliveryAdvice:
        return DeliveryAdvice(
            generated_at=datetime(2026, 7, 12, tzinfo=UTC),
            summary="unused",
            recommendations=(),
        )

    async def reflect(
        self,
        *,
        persona: Persona,
        feedback: Sequence[AdviceFeedback],
        current_guidance: str | None,
    ) -> str:
        self.reflect_calls.append((persona, len(feedback), current_guidance))
        if self.on_reflect is not None:
            await self.on_reflect()
        return self.guidance


async def _post_feedback(
    client: AsyncClient,
    persona: str = "agile_coach",
    advice_summary: str = "Flow is healthy.",
) -> None:
    response = await client.post(
        f"/api/personas/{persona}/feedback",
        json={"rating": "up", "comment": "spot on", "advice_summary": advice_summary},
    )
    assert response.status_code == 201


async def test_feedback_roundtrip(client: AsyncClient) -> None:
    response = await client.post(
        "/api/personas/agile_coach/feedback",
        json={"rating": "down", "comment": None, "advice_summary": "Hire more people."},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["persona"] == "agile_coach"
    assert body["rating"] == "down"
    assert body["comment"] is None
    assert body["advice_summary"] == "Hire more people."
    assert "id" in body and "created_at" in body


async def test_feedback_unknown_persona_is_422(client: AsyncClient) -> None:
    response = await client.post(
        "/api/personas/fortune_teller/feedback",
        json={"rating": "up", "comment": None, "advice_summary": "x"},
    )
    assert response.status_code == 422


async def test_feedback_invalid_rating_is_422(client: AsyncClient) -> None:
    response = await client.post(
        "/api/personas/agile_coach/feedback",
        json={"rating": "meh", "comment": None, "advice_summary": "x"},
    )
    assert response.status_code == 422


async def test_guidance_is_empty_initially(client: AsyncClient) -> None:
    response = await client.get("/api/personas/agile_coach/guidance")
    assert response.status_code == 200
    assert response.json() == []


async def test_reflect_409_when_unconfigured(
    client: AsyncClient, settings_env: Callable[..., None]
) -> None:
    settings_env(openrouter_api_key="")
    response = await client.post("/api/personas/agile_coach/reflect")
    assert response.status_code == 409
    assert "OPENROUTER" in response.json()["detail"]


async def test_reflect_409_when_no_new_feedback(
    client: AsyncClient, test_app: FastAPI
) -> None:
    test_app.dependency_overrides[get_advisor_port] = lambda: FakeReflectingAdvisor()
    response = await client.post("/api/personas/agile_coach/reflect")
    assert response.status_code == 409
    assert "feedback" in response.json()["detail"].lower()


async def test_reflect_creates_a_guidance_version(
    client: AsyncClient, test_app: FastAPI
) -> None:
    fake = FakeReflectingAdvisor()
    test_app.dependency_overrides[get_advisor_port] = lambda: fake
    await _post_feedback(client)

    response = await client.post("/api/personas/agile_coach/reflect")

    assert response.status_code == 201
    body = response.json()
    assert body["version"] == 1
    assert body["guidance"] == "Lead with WIP limits."
    assert fake.reflect_calls == [(Persona.AGILE_COACH, 1, None)]

    listed = await client.get("/api/personas/agile_coach/guidance")
    assert [g["version"] for g in listed.json()] == [1]

    # the feedback is consumed: a second reflect without new feedback is 409
    assert (await client.post("/api/personas/agile_coach/reflect")).status_code == 409


async def test_second_reflection_receives_current_guidance(
    client: AsyncClient, test_app: FastAPI
) -> None:
    fake = FakeReflectingAdvisor()
    test_app.dependency_overrides[get_advisor_port] = lambda: fake
    await _post_feedback(client)
    await client.post("/api/personas/agile_coach/reflect")
    await _post_feedback(client)
    fake.guidance = "Prefer flow-efficiency actions."

    response = await client.post("/api/personas/agile_coach/reflect")

    assert response.status_code == 201
    assert response.json()["version"] == 2
    assert fake.reflect_calls[1] == (Persona.AGILE_COACH, 1, "Lead with WIP limits.")


async def test_reflect_survives_feedback_arriving_mid_call(
    client: AsyncClient, test_app: FastAPI
) -> None:
    """Feedback posted while reflect() is in flight must not be lost.

    Regression test for the race fixed in app/api/personas.py: the
    "already distilled" watermark must be captured from the pending
    feedback's own created_at BEFORE calling advisor.reflect(), not from
    the new guidance row's created_at (stamped after the LLM returns). A
    feedback item arriving mid-call would otherwise fall between the two
    timestamps and be silently dropped forever — the next reflect would
    see zero pending feedback and 409 instead of picking it up.
    """
    fake = FakeReflectingAdvisor()

    async def post_mid_flight_feedback() -> None:
        await _post_feedback(client, advice_summary="Mid-flight feedback.")

    fake.on_reflect = post_mid_flight_feedback
    test_app.dependency_overrides[get_advisor_port] = lambda: fake
    await _post_feedback(client)  # F1, before reflect starts

    first = await client.post("/api/personas/agile_coach/reflect")
    assert first.status_code == 201
    assert first.json()["version"] == 1

    # F2 (posted from on_reflect, mid-call) must still be pending: this must
    # succeed with a new version, not 409 "no pending feedback".
    second = await client.post("/api/personas/agile_coach/reflect")
    assert second.status_code == 201
    assert second.json()["version"] == 2

    assert fake.reflect_calls[0] == (Persona.AGILE_COACH, 1, None)
    # The second call saw exactly F2 — proof it wasn't silently dropped.
    assert fake.reflect_calls[1] == (Persona.AGILE_COACH, 1, "Lead with WIP limits.")


async def test_restore_re_adds_old_text_as_new_version(
    client: AsyncClient, test_app: FastAPI
) -> None:
    fake = FakeReflectingAdvisor(guidance="Version one text.")
    test_app.dependency_overrides[get_advisor_port] = lambda: fake
    await _post_feedback(client)
    await client.post("/api/personas/agile_coach/reflect")
    await _post_feedback(client)
    fake.guidance = "Version two text."
    await client.post("/api/personas/agile_coach/reflect")

    response = await client.post("/api/personas/agile_coach/guidance/1/restore")

    assert response.status_code == 201
    body = response.json()
    assert body["version"] == 3
    assert body["guidance"] == "Version one text."


async def test_restore_unknown_version_is_404(client: AsyncClient) -> None:
    response = await client.post("/api/personas/agile_coach/guidance/9/restore")
    assert response.status_code == 404
