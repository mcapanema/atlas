from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.incidents.entities import ServiceIncident
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UTCDateTime
from app.infrastructure.repositories.batching import chunked


class ServiceIncidentModel(Base):
    __tablename__ = "service_incidents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    restored_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    services: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_domain(self) -> ServiceIncident:
        return ServiceIncident(
            id=self.id,
            organization_id=self.organization_id,
            external_id=self.external_id,
            title=self.title,
            opened_at=self.opened_at,
            restored_at=self.restored_at,
            services=tuple(self.services),
            severity=self.severity,
            url=self.url,
        )

    @classmethod
    def from_domain(cls, incident: ServiceIncident) -> "ServiceIncidentModel":
        return cls(
            id=incident.id,
            organization_id=incident.organization_id,
            external_id=incident.external_id,
            title=incident.title,
            opened_at=incident.opened_at,
            restored_at=incident.restored_at,
            services=list(incident.services),
            severity=incident.severity,
            url=incident.url,
        )


class SqlAlchemyServiceIncidentRepository:
    """SQLAlchemy adapter for the ServiceIncidentRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, incident: ServiceIncident) -> None:
        self._session.add(ServiceIncidentModel.from_domain(incident))
        await self._session.flush()

    async def update(self, incident: ServiceIncident) -> None:
        await self._session.merge(ServiceIncidentModel.from_domain(incident))
        await self._session.flush()

    async def get_by_external_ids(self, external_ids: list[str]) -> dict[str, ServiceIncident]:
        found: dict[str, ServiceIncident] = {}
        for chunk in chunked(external_ids):
            result = await self._session.execute(
                select(ServiceIncidentModel).where(ServiceIncidentModel.external_id.in_(chunk))
            )
            for model in result.scalars():
                found[model.external_id] = model.to_domain()
        return found

    async def list(self, organization_id: UUID) -> list[ServiceIncident]:
        result = await self._session.execute(
            select(ServiceIncidentModel)
            .where(ServiceIncidentModel.organization_id == organization_id)
            .order_by(ServiceIncidentModel.opened_at)
        )
        return [model.to_domain() for model in result.scalars()]
