from datetime import datetime
from uuid import UUID

from sqlalchemy import Index, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.advisor.entities import AdviceFeedback, Persona, PersonaGuidance
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UTCDateTime


class AdviceFeedbackModel(Base):
    __tablename__ = "advice_feedback"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    persona: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    rating: Mapped[str] = mapped_column(String(10), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    advice_summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    def to_domain(self) -> AdviceFeedback:
        return AdviceFeedback(
            id=self.id,
            persona=Persona(self.persona),
            rating=self.rating,
            comment=self.comment,
            advice_summary=self.advice_summary,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, feedback: AdviceFeedback) -> "AdviceFeedbackModel":
        return cls(
            id=feedback.id,
            persona=feedback.persona.value,
            rating=feedback.rating,
            comment=feedback.comment,
            advice_summary=feedback.advice_summary,
            created_at=feedback.created_at,
        )


class PersonaGuidanceModel(Base):
    __tablename__ = "persona_guidance"
    __table_args__ = (
        Index("ix_persona_guidance_persona_version", "persona", "version", unique=True),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    persona: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    guidance: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    def to_domain(self) -> PersonaGuidance:
        return PersonaGuidance(
            id=self.id,
            persona=Persona(self.persona),
            version=self.version,
            guidance=self.guidance,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, guidance: PersonaGuidance) -> "PersonaGuidanceModel":
        return cls(
            id=guidance.id,
            persona=guidance.persona.value,
            version=guidance.version,
            guidance=guidance.guidance,
            created_at=guidance.created_at,
        )


class SqlAlchemyAdviceFeedbackRepository:
    """SQLAlchemy adapter for the AdviceFeedbackRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, feedback: AdviceFeedback) -> None:
        self._session.add(AdviceFeedbackModel.from_domain(feedback))
        await self._session.flush()

    async def list_for_persona(
        self, persona: Persona, *, since: datetime | None = None
    ) -> list[AdviceFeedback]:
        stmt = (
            select(AdviceFeedbackModel)
            .where(AdviceFeedbackModel.persona == persona.value)
            .order_by(AdviceFeedbackModel.created_at)
        )
        if since is not None:
            stmt = stmt.where(AdviceFeedbackModel.created_at > since)
        result = await self._session.execute(stmt)
        return [model.to_domain() for model in result.scalars()]


class SqlAlchemyPersonaGuidanceRepository:
    """SQLAlchemy adapter for the PersonaGuidanceRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, guidance: PersonaGuidance) -> None:
        self._session.add(PersonaGuidanceModel.from_domain(guidance))
        await self._session.flush()

    async def latest(self, persona: Persona) -> PersonaGuidance | None:
        stmt = (
            select(PersonaGuidanceModel)
            .where(PersonaGuidanceModel.persona == persona.value)
            .order_by(PersonaGuidanceModel.version.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        return model.to_domain() if model else None

    async def list_versions(self, persona: Persona) -> list[PersonaGuidance]:
        stmt = (
            select(PersonaGuidanceModel)
            .where(PersonaGuidanceModel.persona == persona.value)
            .order_by(PersonaGuidanceModel.version.desc())
        )
        result = await self._session.execute(stmt)
        return [model.to_domain() for model in result.scalars()]

    async def get_version(self, persona: Persona, version: int) -> PersonaGuidance | None:
        stmt = select(PersonaGuidanceModel).where(
            PersonaGuidanceModel.persona == persona.value,
            PersonaGuidanceModel.version == version,
        )
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        return model.to_domain() if model else None
