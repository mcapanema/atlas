from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.events.service import EventService
from app.application.forecasting.service import ForecastService
from app.application.metrics.service import MetricsService
from app.application.organizations.service import OrganizationService
from app.application.projects.service import ProjectService
from app.application.sync.service import SyncService
from app.application.teams.service import TeamService
from app.application.work_items.service import WorkItemService
from app.config import get_settings
from app.domain.sync.port import DeliveryDataSource
from app.infrastructure.connectors.linear.client import LinearGraphQLClient
from app.infrastructure.connectors.linear.datasource import LinearDataSource
from app.infrastructure.repositories.events import SqlAlchemyEventRepository
from app.infrastructure.repositories.organizations import SqlAlchemyOrganizationRepository
from app.infrastructure.repositories.projects import SqlAlchemyProjectRepository
from app.infrastructure.repositories.teams import SqlAlchemyTeamRepository
from app.infrastructure.repositories.work_items import SqlAlchemyWorkItemRepository


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


def get_project_service(session: SessionDep) -> ProjectService:
    return ProjectService(SqlAlchemyProjectRepository(session))


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]


def get_work_item_service(session: SessionDep) -> WorkItemService:
    return WorkItemService(SqlAlchemyWorkItemRepository(session))


WorkItemServiceDep = Annotated[WorkItemService, Depends(get_work_item_service)]


def get_event_service(session: SessionDep) -> EventService:
    return EventService(SqlAlchemyEventRepository(session))


EventServiceDep = Annotated[EventService, Depends(get_event_service)]


def get_metrics_service(session: SessionDep) -> MetricsService:
    return MetricsService(
        SqlAlchemyWorkItemRepository(session),
        SqlAlchemyEventRepository(session),
    )


MetricsServiceDep = Annotated[MetricsService, Depends(get_metrics_service)]


def get_forecast_service(session: SessionDep) -> ForecastService:
    return ForecastService(
        SqlAlchemyWorkItemRepository(session),
        SqlAlchemyEventRepository(session),
    )


ForecastServiceDep = Annotated[ForecastService, Depends(get_forecast_service)]


def get_delivery_data_source() -> DeliveryDataSource:
    settings = get_settings()
    if not settings.linear_api_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Linear connector is not configured; set ATLAS_LINEAR_API_KEY",
        )
    return LinearDataSource(LinearGraphQLClient(settings.linear_api_key))


DeliveryDataSourceDep = Annotated[DeliveryDataSource, Depends(get_delivery_data_source)]


def get_sync_service(session: SessionDep, source: DeliveryDataSourceDep) -> SyncService:
    return SyncService(
        source,
        SqlAlchemyOrganizationRepository(session),
        SqlAlchemyTeamRepository(session),
        SqlAlchemyProjectRepository(session),
        SqlAlchemyWorkItemRepository(session),
        SqlAlchemyEventRepository(session),
    )


SyncServiceDep = Annotated[SyncService, Depends(get_sync_service)]
