from collections.abc import Collection
from datetime import datetime
from uuid import UUID

from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.people.entities import Person
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UTCDateTime
from app.infrastructure.repositories.batching import chunked


class PersonModel(Base):
    __tablename__ = "people"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    # ponytail: no FK to organizations, like teams — add with organization lifecycle management
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    def to_domain(self) -> Person:
        return Person(
            id=self.id,
            organization_id=self.organization_id,
            name=self.name,
            external_id=self.external_id,
            email=self.email,
            display_name=self.display_name,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, person: Person) -> "PersonModel":
        return cls(
            id=person.id,
            organization_id=person.organization_id,
            name=person.name,
            external_id=person.external_id,
            email=person.email,
            display_name=person.display_name,
            created_at=person.created_at,
        )


class SqlAlchemyPersonRepository:
    """SQLAlchemy adapter for the PersonRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, person: Person) -> None:
        self._session.add(PersonModel.from_domain(person))
        await self._session.flush()

    async def update(self, person: Person) -> None:
        await self._session.merge(PersonModel.from_domain(person))
        await self._session.flush()

    async def get(self, person_id: UUID) -> Person | None:
        model = await self._session.get(PersonModel, person_id)
        return model.to_domain() if model is not None else None

    async def list(self, organization_id: UUID | None = None) -> list[Person]:
        query = select(PersonModel)
        if organization_id is not None:
            query = query.where(PersonModel.organization_id == organization_id)
        query = query.order_by(
            func.lower(func.coalesce(PersonModel.display_name, PersonModel.name)), PersonModel.id
        )
        result = await self._session.execute(query)
        return [model.to_domain() for model in result.scalars()]

    async def get_by_external_ids(self, external_ids: Collection[str]) -> dict[str, Person]:
        people: dict[str, Person] = {}
        for chunk in chunked(list(external_ids)):
            result = await self._session.execute(
                select(PersonModel).where(PersonModel.external_id.in_(chunk))
            )
            for model in result.scalars():
                if model.external_id is not None:
                    people[model.external_id] = model.to_domain()
        return people
