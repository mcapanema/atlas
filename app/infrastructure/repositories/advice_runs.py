from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Index, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.advisor.entities import (
    DeliveryAdvice,
    MeetingPrep,
    MeetingType,
    Persona,
    Recommendation,
    TalkingPoint,
)
from app.domain.advisor.runs import AdviceRun, RunStatus
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UTCDateTime

_MEETING_PERSONAS = {m.value for m in MeetingType}


def _result_to_json(result: DeliveryAdvice | MeetingPrep | None) -> dict[str, Any] | None:
    if isinstance(result, DeliveryAdvice):
        return {
            "generated_at": result.generated_at.isoformat(),
            "summary": result.summary,
            "recommendations": [
                {
                    "title": r.title,
                    "priority": r.priority,
                    "problem": r.problem,
                    "root_cause": r.root_cause,
                    "action": r.action,
                    "evidence": list(r.evidence),
                }
                for r in result.recommendations
            ],
        }
    if isinstance(result, MeetingPrep):
        return {
            "meeting": result.meeting.value,
            "generated_at": result.generated_at.isoformat(),
            "headline": result.headline,
            "talking_points": [
                {
                    "point": t.point,
                    "detail": t.detail,
                    "evidence": list(t.evidence),
                    "needs_decision": t.needs_decision,
                }
                for t in result.talking_points
            ],
        }
    return None


def _result_from_json(
    persona: Persona, data: dict[str, Any] | None
) -> DeliveryAdvice | MeetingPrep | None:
    if data is None:
        return None
    generated_at = datetime.fromisoformat(data["generated_at"])
    if persona.value in _MEETING_PERSONAS:
        return MeetingPrep(
            meeting=MeetingType(data["meeting"]),
            generated_at=generated_at,
            headline=data["headline"],
            talking_points=tuple(
                TalkingPoint(
                    point=t["point"],
                    detail=t["detail"],
                    evidence=tuple(t["evidence"]),
                    needs_decision=t["needs_decision"],
                )
                for t in data["talking_points"]
            ),
        )
    return DeliveryAdvice(
        generated_at=generated_at,
        summary=data["summary"],
        recommendations=tuple(
            Recommendation(
                title=r["title"],
                priority=r["priority"],
                problem=r["problem"],
                root_cause=r["root_cause"],
                action=r["action"],
                evidence=tuple(r["evidence"]),
            )
            for r in data["recommendations"]
        ),
    )


class AdviceRunModel(Base):
    __tablename__ = "advice_runs"
    __table_args__ = (
        Index("ix_advice_runs_team_key", "team_id", "persona", "params", "requested_at"),
        Index("ix_advice_runs_project_key", "project_id", "persona", "params", "requested_at"),
        Index("ix_advice_runs_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    team_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    project_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    persona: Mapped[str] = mapped_column(String(32), nullable=False)
    params: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    def to_domain(self) -> AdviceRun:
        persona = Persona(self.persona)
        return AdviceRun(
            id=self.id,
            team_id=self.team_id,
            project_id=self.project_id,
            persona=persona,
            params=self.params,
            status=RunStatus(self.status),
            result=_result_from_json(persona, self.result),
            error=self.error,
            requested_at=self.requested_at,
            finished_at=self.finished_at,
        )

    @classmethod
    def from_domain(cls, run: AdviceRun) -> "AdviceRunModel":
        model = cls(
            id=run.id,
            team_id=run.team_id,
            project_id=run.project_id,
            persona=run.persona.value,
            params=run.params,
            requested_at=run.requested_at,
        )
        model.apply(run)
        return model

    def apply(self, run: AdviceRun) -> None:
        """Copy the mutable outcome fields (status, result, error, finished_at)."""
        self.status = run.status.value
        self.result = _result_to_json(run.result)
        self.error = run.error
        self.finished_at = run.finished_at


class SqlAlchemyAdviceRunRepository:
    """SQLAlchemy adapter for the AdviceRunRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, run: AdviceRun) -> None:
        self._session.add(AdviceRunModel.from_domain(run))
        await self._session.flush()

    async def get(self, run_id: UUID) -> AdviceRun | None:
        model = await self._session.get(AdviceRunModel, run_id)
        return model.to_domain() if model else None

    async def update(self, run: AdviceRun) -> None:
        model = await self._session.get(AdviceRunModel, run.id)
        if model is None:
            raise LookupError(f"advice run {run.id} not found")
        model.apply(run)
        await self._session.flush()

    async def latest(
        self,
        *,
        team_id: UUID | None,
        project_id: UUID | None,
        persona: Persona,
        params: str,
    ) -> AdviceRun | None:
        scope = (
            AdviceRunModel.team_id == team_id
            if team_id is not None
            else AdviceRunModel.project_id == project_id
        )
        stmt = (
            select(AdviceRunModel)
            .where(scope, AdviceRunModel.persona == persona.value, AdviceRunModel.params == params)
            .order_by(AdviceRunModel.requested_at.desc())
            .limit(1)
        )
        model = (await self._session.execute(stmt)).scalars().first()
        return model.to_domain() if model else None

    async def list_running(self) -> list[AdviceRun]:
        stmt = (
            select(AdviceRunModel)
            .where(AdviceRunModel.status == RunStatus.RUNNING.value)
            .order_by(AdviceRunModel.requested_at)
        )
        return [m.to_domain() for m in (await self._session.execute(stmt)).scalars()]
