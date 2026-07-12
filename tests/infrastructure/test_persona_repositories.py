from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.advisor.entities import AdviceFeedback, Persona, PersonaGuidance
from app.infrastructure.repositories.personas import (
    SqlAlchemyAdviceFeedbackRepository,
    SqlAlchemyPersonaGuidanceRepository,
)

_T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
_T1 = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)
_T2 = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)


def _feedback(created_at: datetime, rating: str = "up") -> AdviceFeedback:
    return AdviceFeedback(
        persona=Persona.AGILE_COACH,
        rating=rating,
        advice_summary="Flow is healthy.",
        comment="spot on" if rating == "up" else None,
        created_at=created_at,
    )


async def test_feedback_roundtrip_ordering_and_since_filter(session: AsyncSession) -> None:
    repo = SqlAlchemyAdviceFeedbackRepository(session)
    early, late = _feedback(_T0), _feedback(_T2, rating="down")
    await repo.add(late)
    await repo.add(early)
    await repo.add(
        AdviceFeedback(
            persona=Persona.DELIVERY_ANALYST,
            rating="up",
            advice_summary="other persona",
            created_at=_T1,
        )
    )

    assert await repo.list_for_persona(Persona.AGILE_COACH) == [early, late]
    assert await repo.list_for_persona(Persona.AGILE_COACH, since=_T1) == [late]


async def test_guidance_latest_versions_desc_and_get_version(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyPersonaGuidanceRepository(session)
    v1 = PersonaGuidance(
        persona=Persona.AGILE_COACH, version=1, guidance="Be concise.", created_at=_T0
    )
    v2 = PersonaGuidance(
        persona=Persona.AGILE_COACH, version=2, guidance="Lead with WIP.", created_at=_T1
    )
    await repo.add(v2)
    await repo.add(v1)

    assert await repo.latest(Persona.AGILE_COACH) == v2
    assert await repo.latest(Persona.DELIVERY_ANALYST) is None
    assert await repo.list_versions(Persona.AGILE_COACH) == [v2, v1]
    assert await repo.get_version(Persona.AGILE_COACH, 1) == v1
    assert await repo.get_version(Persona.AGILE_COACH, 9) is None


async def test_duplicate_guidance_version_is_rejected(session: AsyncSession) -> None:
    repo = SqlAlchemyPersonaGuidanceRepository(session)
    await repo.add(
        PersonaGuidance(persona=Persona.AGILE_COACH, version=1, guidance="a", created_at=_T0)
    )
    with pytest.raises(IntegrityError):
        await repo.add(
            PersonaGuidance(
                persona=Persona.AGILE_COACH, version=1, guidance="b", created_at=_T1
            )
        )
