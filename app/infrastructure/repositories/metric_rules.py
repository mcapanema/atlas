from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Index, String, Text, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.metric_rules.entities import RecomputeState, RecomputeStatus, RuleOverrides
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UTCDateTime


class MetricRuleOverridesModel(Base):
    __tablename__ = "metric_rule_overrides"
    __table_args__ = (
        # One row per (organization, team). NULLs are distinct in a unique
        # index, so the organization's own row (team_id NULL) needs a partial one.
        Index("ix_metric_rule_overrides_org_team", "organization_id", "team_id", unique=True),
        Index(
            "ix_metric_rule_overrides_org_default",
            "organization_id",
            unique=True,
            sqlite_where=text("team_id IS NULL"),
            postgresql_where=text("team_id IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    # ponytail: no FK to organizations, same as teams.organization_id
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    team_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("teams.id"), nullable=True)
    overrides: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    recompute_state: Mapped[str] = mapped_column(String(16), nullable=False)
    recompute_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    recompute_finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    recompute_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    def to_domain(self) -> RuleOverrides:
        return RuleOverrides(
            id=self.id,
            organization_id=self.organization_id,
            team_id=self.team_id,
            overrides=dict(self.overrides),
            recompute=RecomputeStatus(
                state=cast(RecomputeState, self.recompute_state),
                started_at=self.recompute_started_at,
                finished_at=self.recompute_finished_at,
                error=self.recompute_error,
            ),
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, row: RuleOverrides) -> "MetricRuleOverridesModel":
        model = cls(
            id=row.id,
            organization_id=row.organization_id,
            team_id=row.team_id,
            overrides=dict(row.overrides),
            updated_at=row.updated_at,
        )
        model.set_recompute(row.recompute)
        return model

    def set_recompute(self, status: RecomputeStatus) -> None:
        self.recompute_state = status.state
        self.recompute_started_at = status.started_at
        self.recompute_finished_at = status.finished_at
        self.recompute_error = status.error


class SqlAlchemyMetricRuleOverridesRepository:
    """SQLAlchemy adapter for the MetricRuleOverridesRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, organization_id: UUID, *, team_id: UUID | None = None
    ) -> RuleOverrides | None:
        found = await self._find(organization_id, team_id)
        return found.to_domain() if found is not None else None

    async def _find(
        self, organization_id: UUID, team_id: UUID | None
    ) -> MetricRuleOverridesModel | None:
        model = MetricRuleOverridesModel
        team_match = model.team_id.is_(None) if team_id is None else model.team_id == team_id
        result = await self._session.execute(
            select(model).where(model.organization_id == organization_id, team_match)
        )
        return result.scalars().one_or_none()

    async def list_for_organization(self, organization_id: UUID) -> list[RuleOverrides]:
        result = await self._session.execute(
            select(MetricRuleOverridesModel).where(
                MetricRuleOverridesModel.organization_id == organization_id
            )
        )
        return [model.to_domain() for model in result.scalars()]

    async def list_recomputing(self) -> list[RuleOverrides]:
        result = await self._session.execute(
            select(MetricRuleOverridesModel).where(
                MetricRuleOverridesModel.team_id.is_(None),
                MetricRuleOverridesModel.recompute_state == "running",
            )
        )
        return [model.to_domain() for model in result.scalars()]

    async def save(self, overrides: RuleOverrides) -> None:
        # An existing row keeps its recompute_* columns: the recompute runner
        # owns them (save_recompute), so a concurrent overrides edit can't
        # overwrite its progress.
        existing = await self._session.get(MetricRuleOverridesModel, overrides.id)
        if existing is None:
            self._session.add(MetricRuleOverridesModel.from_domain(overrides))
        else:
            existing.overrides = dict(overrides.overrides)
            existing.updated_at = overrides.updated_at
        await self._session.flush()

    async def save_recompute(self, organization_id: UUID, status: RecomputeStatus) -> None:
        """Write only the recompute_* columns of the organization's row."""
        existing = await self._find(organization_id, None)
        if existing is None:
            await self.save(RuleOverrides(organization_id=organization_id, recompute=status))
            return
        existing.set_recompute(status)  # updated_at stays "overrides last edited"
        await self._session.flush()
