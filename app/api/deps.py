from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.organizations.service import OrganizationService
from app.application.teams.service import TeamService
from app.infrastructure.repositories.organizations import SqlAlchemyOrganizationRepository
from app.infrastructure.repositories.teams import SqlAlchemyTeamRepository


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    # ponytail: request-scoped commit-on-success. Introduce an explicit Unit of Work
    # only when a single request must coordinate writes across multiple repositories.
    sessionmaker = request.app.state.sessionmaker
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_organization_service(session: SessionDep) -> OrganizationService:
    return OrganizationService(SqlAlchemyOrganizationRepository(session))


OrganizationServiceDep = Annotated[OrganizationService, Depends(get_organization_service)]


def get_team_service(session: SessionDep) -> TeamService:
    return TeamService(SqlAlchemyTeamRepository(session))


TeamServiceDep = Annotated[TeamService, Depends(get_team_service)]
