from dataclasses import replace
from uuid import UUID

from app.application.metric_rules.resolver import MetricRulesResolver
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules
from app.domain.work_items.entities import DEFAULT_STATE, WorkItem, WorkItemType
from app.domain.work_items.repository import WorkItemRepository


class WorkItemService:
    """Application use cases for Work Items."""

    def __init__(
        self, repository: WorkItemRepository, rules: MetricRulesResolver | None = None
    ) -> None:
        self._repository = repository
        self._rules = rules

    async def create_work_item(
        self,
        team_id: UUID,
        title: str,
        type: WorkItemType = WorkItemType.TASK,
        state: str = DEFAULT_STATE,
        project_id: UUID | None = None,
        external_id: str | None = None,
    ) -> WorkItem:
        work_item = WorkItem(
            team_id=team_id,
            title=title,
            type=type,
            state=state,
            project_id=project_id,
            external_id=external_id,
        )
        await self._repository.add(work_item)
        return work_item

    async def list_work_items(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[WorkItem]:
        return await self._typed(
            await self._repository.list(
                team_id=team_id, project_id=project_id, limit=limit, offset=offset
            )
        )

    async def count_work_items(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> int:
        return await self._repository.count(team_id=team_id, project_id=project_id)

    async def list_states(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[str]:
        return await self._repository.list_states(team_id=team_id, project_id=project_id)

    async def get_work_item(self, work_item_id: UUID) -> WorkItem | None:
        item = await self._repository.get(work_item_id)
        return None if item is None else (await self._typed([item]))[0]

    async def list_labels(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[str]:
        return await self._repository.list_labels(team_id=team_id, project_id=project_id)

    async def team_rules(self, team_id: UUID) -> MetricRules:
        """The team's effective metric rules (built-in without a resolver)."""
        return DEFAULT_RULES if self._rules is None else await self._rules.team_rules(team_id)

    async def _typed(self, items: list[WorkItem]) -> list[WorkItem]:
        """Items with their effective type — their team's type_labels rule, else the stored type."""
        by_team: dict[UUID, MetricRules] = {}
        typed: list[WorkItem] = []
        for item in items:
            if item.team_id not in by_team:
                by_team[item.team_id] = await self.team_rules(item.team_id)
            typed.append(replace(item, type=by_team[item.team_id].type_of(item)))
        return typed
