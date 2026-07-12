from datetime import UTC, datetime, timedelta

from app.application.personas.service import PersonaService
from app.domain.advisor.entities import AdviceFeedback, Persona, PersonaGuidance
from tests.fakes import InMemoryAdviceFeedbackRepository, InMemoryPersonaGuidanceRepository

_T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def _service() -> tuple[
    PersonaService, InMemoryAdviceFeedbackRepository, InMemoryPersonaGuidanceRepository
]:
    feedback = InMemoryAdviceFeedbackRepository()
    guidance = InMemoryPersonaGuidanceRepository()
    return PersonaService(feedback, guidance), feedback, guidance


async def test_record_feedback_persists_and_returns_the_entity() -> None:
    service, feedback_repo, _ = _service()

    feedback = await service.record_feedback(
        persona=Persona.AGILE_COACH,
        rating="up",
        comment="spot on",
        advice_summary="Flow is healthy.",
    )

    assert await feedback_repo.list_for_persona(Persona.AGILE_COACH) == [feedback]
    assert feedback.comment == "spot on"


async def test_active_guidance_is_none_before_any_reflection() -> None:
    service, _, _ = _service()
    assert await service.active_guidance(Persona.AGILE_COACH) is None
    assert await service.list_guidance(Persona.AGILE_COACH) == []


async def test_add_guidance_increments_versions() -> None:
    service, _, _ = _service()

    first = await service.add_guidance(Persona.AGILE_COACH, "Be concise.")
    second = await service.add_guidance(Persona.AGILE_COACH, "Lead with WIP.")

    assert (first.version, second.version) == (1, 2)
    active = await service.active_guidance(Persona.AGILE_COACH)
    assert active is not None and active.guidance == "Lead with WIP."
    assert [g.version for g in await service.list_guidance(Persona.AGILE_COACH)] == [2, 1]


async def test_pending_feedback_excludes_feedback_before_latest_guidance() -> None:
    service, feedback_repo, guidance_repo = _service()
    old = AdviceFeedback(
        persona=Persona.AGILE_COACH, rating="up", advice_summary="old", created_at=_T0
    )
    await feedback_repo.add(old)
    await guidance_repo.add(
        PersonaGuidance(
            persona=Persona.AGILE_COACH,
            version=1,
            guidance="g",
            created_at=_T0 + timedelta(hours=1),
        )
    )
    new = AdviceFeedback(
        persona=Persona.AGILE_COACH,
        rating="down",
        advice_summary="new",
        created_at=_T0 + timedelta(hours=2),
    )
    await feedback_repo.add(new)

    assert await service.pending_feedback(Persona.AGILE_COACH) == [new]


async def test_pending_feedback_is_everything_when_no_guidance_exists() -> None:
    service, feedback_repo, _ = _service()
    feedback = AdviceFeedback(
        persona=Persona.AGILE_COACH, rating="up", advice_summary="x", created_at=_T0
    )
    await feedback_repo.add(feedback)

    assert await service.pending_feedback(Persona.AGILE_COACH) == [feedback]


async def test_restore_copies_old_text_as_a_new_version() -> None:
    service, _, _ = _service()
    await service.add_guidance(Persona.AGILE_COACH, "Be concise.")
    await service.add_guidance(Persona.AGILE_COACH, "Lead with WIP.")

    restored = await service.restore_guidance(Persona.AGILE_COACH, 1)

    assert restored is not None
    assert restored.version == 3
    assert restored.guidance == "Be concise."


async def test_restore_unknown_version_returns_none() -> None:
    service, _, _ = _service()
    assert await service.restore_guidance(Persona.AGILE_COACH, 9) is None
