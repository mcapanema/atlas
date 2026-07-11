from datetime import datetime
from uuid import UUID

from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.organizations.entities import Organization
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UTCDateTime


class OrganizationModel(Base):
    __tablename__ = "organizations"

    # Uuid renders as native uuid on PostgreSQL and CHAR(32) on SQLite — portable.
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    def to_domain(self) -> Organization:
        return Organization(id=self.id, name=self.name, created_at=self.created_at)

    @classmethod
    def from_domain(cls, organization: Organization) -> "OrganizationModel":
        return cls(
            id=organization.id,
            name=organization.name,
            created_at=organization.created_at,
        )


class SqlAlchemyOrganizationRepository:
    """SQLAlchemy adapter for the OrganizationRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, organization: Organization) -> None:
        self._session.add(OrganizationModel.from_domain(organization))
        await self._session.flush()

    async def list(self) -> list[Organization]:
        result = await self._session.execute(
            select(OrganizationModel).order_by(OrganizationModel.created_at)
        )
        return [model.to_domain() for model in result.scalars()]

    async def get(self, organization_id: UUID) -> Organization | None:
        model = await self._session.get(OrganizationModel, organization_id)
        return model.to_domain() if model is not None else None
