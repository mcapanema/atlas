from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.advisor.service import AdvisorService
from app.application.events.service import EventService
from app.application.forecasting.service import ForecastService
from app.application.metric_rules.resolver import MetricRulesResolver
from app.application.metric_rules.service import MetricRulesService
from app.application.metrics.service import MetricsService
from app.application.organizations.service import OrganizationService
from app.application.personas.service import PersonaService
from app.application.projects.service import ProjectService
from app.application.snapshots.service import SnapshotService
from app.application.sync.service import SyncService
from app.application.sync_schedules.service import SyncScheduleService
from app.application.teams.service import TeamService
from app.application.work_items.service import WorkItemService
from app.config import get_settings
from app.domain.advisor.port import AdvisorPort
from app.domain.sync.port import DeliveryDataSource
from app.infrastructure.ai.advisor import OpenRouterAdvisor
from app.infrastructure.connectors.linear.client import LinearGraphQLClient
from app.infrastructure.connectors.linear.datasource import LinearDataSource
from app.infrastructure.repositories.events import SqlAlchemyEventRepository
from app.infrastructure.repositories.metric_rules import SqlAlchemyMetricRuleOverridesRepository
from app.infrastructure.repositories.organizations import SqlAlchemyOrganizationRepository
from app.infrastructure.repositories.personas import (
    SqlAlchemyAdviceFeedbackRepository,
    SqlAlchemyPersonaGuidanceRepository,
)
from app.infrastructure.repositories.projects import SqlAlchemyProjectRepository
from app.infrastructure.repositories.snapshots import (
    SqlAlchemyForecastSnapshotRepository,
    SqlAlchemyMetricSnapshotRepository,
)
from app.infrastructure.repositories.sync_schedules import SqlAlchemySyncScheduleRepository
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


# scope="function": the teardown above (the commit) runs when the route
# returns, BEFORE the response is sent — so a 2xx means the write is
# durable and a failed commit is a 5xx (or 409 via the IntegrityError
# handler). FastAPI's default "request" scope commits after the response
# went out: a failed commit was a silent rollback behind a success
# (review 2026-10-04, F1).
SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]


def rules_resolver_for(session: AsyncSession) -> MetricRulesResolver:
    return MetricRulesResolver(
        SqlAlchemyMetricRuleOverridesRepository(session),
        SqlAlchemyTeamRepository(session),
        SqlAlchemyProjectRepository(session),
    )


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
    return WorkItemService(SqlAlchemyWorkItemRepository(session), rules_resolver_for(session))


WorkItemServiceDep = Annotated[WorkItemService, Depends(get_work_item_service)]


def get_event_service(session: SessionDep) -> EventService:
    return EventService(SqlAlchemyEventRepository(session))


EventServiceDep = Annotated[EventService, Depends(get_event_service)]


def get_metrics_service(session: SessionDep) -> MetricsService:
    return MetricsService(
        SqlAlchemyWorkItemRepository(session),
        SqlAlchemyEventRepository(session),
        rules_resolver_for(session),
        teams=SqlAlchemyTeamRepository(session),
        projects=SqlAlchemyProjectRepository(session),
    )


MetricsServiceDep = Annotated[MetricsService, Depends(get_metrics_service)]


def get_forecast_service(session: SessionDep) -> ForecastService:
    return ForecastService(
        SqlAlchemyWorkItemRepository(session),
        SqlAlchemyEventRepository(session),
        rules_resolver_for(session),
    )


ForecastServiceDep = Annotated[ForecastService, Depends(get_forecast_service)]


def get_advisor_port() -> AdvisorPort:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Advisor is not configured; set ATLAS_OPENROUTER_API_KEY",
        )
    return OpenRouterAdvisor(
        api_key=settings.openrouter_api_key,
        model=settings.advisor_model,
        self_critique=settings.advisor_self_critique,
        max_tokens=settings.advisor_max_tokens,
        timeout_seconds=settings.advisor_timeout_seconds,
    )


AdvisorPortDep = Annotated[AdvisorPort, Depends(get_advisor_port)]


def get_advisor_service(metrics: MetricsServiceDep, forecast: ForecastServiceDep) -> AdvisorService:
    return AdvisorService(metrics, forecast)


AdvisorServiceDep = Annotated[AdvisorService, Depends(get_advisor_service)]


def get_persona_service(session: SessionDep) -> PersonaService:
    return PersonaService(
        SqlAlchemyAdviceFeedbackRepository(session),
        SqlAlchemyPersonaGuidanceRepository(session),
    )


PersonaServiceDep = Annotated[PersonaService, Depends(get_persona_service)]


LINEAR_NOT_CONFIGURED = "Linear connector is not configured; set ATLAS_LINEAR_API_KEY"


def linear_data_source() -> DeliveryDataSource | None:
    """The Linear adapter, or None while ATLAS_LINEAR_API_KEY is unset."""
    settings = get_settings()
    if not settings.linear_api_key:
        return None
    return LinearDataSource(LinearGraphQLClient(settings.linear_api_key))


def get_delivery_data_source() -> DeliveryDataSource:
    source = linear_data_source()
    if source is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=LINEAR_NOT_CONFIGURED)
    return source


DeliveryDataSourceDep = Annotated[DeliveryDataSource, Depends(get_delivery_data_source)]


def sync_service_for(session: AsyncSession, source: DeliveryDataSource) -> SyncService:
    """Built outside a request too: the auto-sync runner opens its own sessions."""
    return SyncService(
        source,
        SqlAlchemyOrganizationRepository(session),
        SqlAlchemyTeamRepository(session),
        SqlAlchemyProjectRepository(session),
        SqlAlchemyWorkItemRepository(session),
        SqlAlchemyEventRepository(session),
    )


def get_sync_service(session: SessionDep, source: DeliveryDataSourceDep) -> SyncService:
    return sync_service_for(session, source)


SyncServiceDep = Annotated[SyncService, Depends(get_sync_service)]


def snapshot_service_for(session: AsyncSession) -> SnapshotService:
    """Built outside a request too: the recompute runner opens its own sessions."""
    work_items = SqlAlchemyWorkItemRepository(session)
    events = SqlAlchemyEventRepository(session)
    rules = rules_resolver_for(session)
    return SnapshotService(
        MetricsService(work_items, events, rules),
        ForecastService(work_items, events, rules),
        SqlAlchemyTeamRepository(session),
        SqlAlchemyProjectRepository(session),
        SqlAlchemyMetricSnapshotRepository(session),
        SqlAlchemyForecastSnapshotRepository(session),
    )


def get_snapshot_service(session: SessionDep) -> SnapshotService:
    return snapshot_service_for(session)


SnapshotServiceDep = Annotated[SnapshotService, Depends(get_snapshot_service)]


def metric_rules_service_for(session: AsyncSession) -> MetricRulesService:
    return MetricRulesService(
        SqlAlchemyMetricRuleOverridesRepository(session),
        SqlAlchemyOrganizationRepository(session),
        SqlAlchemyTeamRepository(session),
        SqlAlchemyProjectRepository(session),
    )


def get_metric_rules_service(session: SessionDep) -> MetricRulesService:
    return metric_rules_service_for(session)


MetricRulesServiceDep = Annotated[MetricRulesService, Depends(get_metric_rules_service)]


def sync_schedule_service_for(session: AsyncSession) -> SyncScheduleService:
    return SyncScheduleService(
        SqlAlchemySyncScheduleRepository(session),
        SqlAlchemyOrganizationRepository(session),
    )


def get_sync_schedule_service(session: SessionDep) -> SyncScheduleService:
    return sync_schedule_service_for(session)


SyncScheduleServiceDep = Annotated[SyncScheduleService, Depends(get_sync_schedule_service)]
