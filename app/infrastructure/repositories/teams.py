from datetime import datetime
from uuid import UUID

from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.teams.entities import Team
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UTCDateTime


class TeamModel(Base):
    __tablename__ = "teams"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    # ponytail: no FK to organizations — add when organization lifecycle management lands
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    def to_domain(self) -> Team:
        return Team(
            id=self.id,
            organization_id=self.organization_id,
            name=self.name,
            external_id=self.external_id,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, team: Team) -> "TeamModel":
        return cls(
            id=team.id,
            organization_id=team.organization_id,
            name=team.name,
            external_id=team.external_id,
            created_at=team.created_at,
        )


class SqlAlchemyTeamRepository:
    """SQLAlchemy adapter for the TeamRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, team: Team) -> None:
        self._session.add(TeamModel.from_domain(team))
        await self._session.flush()

    async def update(self, team: Team) -> None:
        await self._session.merge(TeamModel.from_domain(team))
        await self._session.flush()

    async def list(self) -> list[Team]:
        result = await self._session.execute(
            select(TeamModel).order_by(TeamModel.created_at)
        )
        return [model.to_domain() for model in result.scalars()]

    async def get(self, team_id: UUID) -> Team | None:
        model = await self._session.get(TeamModel, team_id)
        return model.to_domain() if model is not None else None

    async def get_by_external_id(self, external_id: str) -> Team | None:
        result = await self._session.execute(
            select(TeamModel).where(TeamModel.external_id == external_id)
        )
        model = result.scalars().one_or_none()
        return model.to_domain() if model is not None else None
