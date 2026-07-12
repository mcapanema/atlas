"""Shared in-memory test doubles for the domain repository ports.

One canonical fake per port. Service tests import from here instead of
re-declaring per file — naming/behavior drift between copies is how
Protocol/fake mismatches hide. Each fake accepts optional seed data and
stores entities in insertion order (dict keyed by id).
"""

from datetime import date, datetime
from uuid import UUID

from app.domain.advisor.entities import AdviceFeedback, Persona, PersonaGuidance
from app.domain.events.entities import Event
from app.domain.organizations.entities import Organization
from app.domain.projects.entities import Project
from app.domain.snapshots.entities import ForecastSnapshot, MetricSnapshot
from app.domain.sync.source import SourceProject, SourceTeam, SourceWorkItem
from app.domain.teams.entities import Team
from app.domain.work_items.entities import WorkItem


class InMemoryOrganizationRepository:
    def __init__(self, organizations: list[Organization] | None = None) -> None:
        self._orgs: dict[UUID, Organization] = {o.id: o for o in organizations or []}

    async def add(self, organization: Organization) -> None:
        self._orgs[organization.id] = organization

    async def list(self) -> list[Organization]:
        return list(self._orgs.values())

    async def get(self, organization_id: UUID) -> Organization | None:
        return self._orgs.get(organization_id)


class InMemoryTeamRepository:
    def __init__(self, teams: list[Team] | None = None) -> None:
        self._teams: dict[UUID, Team] = {t.id: t for t in teams or []}

    async def add(self, team: Team) -> None:
        self._teams[team.id] = team

    async def update(self, team: Team) -> None:
        self._teams[team.id] = team

    async def list(self) -> list[Team]:
        return list(self._teams.values())

    async def get(self, team_id: UUID) -> Team | None:
        return self._teams.get(team_id)

    async def get_by_external_id(self, external_id: str) -> Team | None:
        return next(
            (t for t in self._teams.values() if t.external_id == external_id), None
        )


class InMemoryProjectRepository:
    def __init__(self, projects: list[Project] | None = None) -> None:
        self._projects: dict[UUID, Project] = {p.id: p for p in projects or []}

    async def add(self, project: Project) -> None:
        self._projects[project.id] = project

    async def update(self, project: Project) -> None:
        self._projects[project.id] = project

    async def list(self) -> list[Project]:
        return list(self._projects.values())

    async def get(self, project_id: UUID) -> Project | None:
        return self._projects.get(project_id)

    async def get_by_external_id(self, external_id: str) -> Project | None:
        return next(
            (p for p in self._projects.values() if p.external_id == external_id), None
        )


class InMemoryWorkItemRepository:
    def __init__(self, items: list[WorkItem] | None = None) -> None:
        self._items: dict[UUID, WorkItem] = {i.id: i for i in items or []}

    async def add(self, work_item: WorkItem) -> None:
        self._items[work_item.id] = work_item

    async def update(self, work_item: WorkItem) -> None:
        self._items[work_item.id] = work_item

    async def list(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[WorkItem]:
        items = [
            item
            for item in self._items.values()
            if (team_id is None or item.team_id == team_id)
            and (project_id is None or item.project_id == project_id)
        ]
        items = items[offset:]
        return items if limit is None else items[:limit]

    async def count(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> int:
        return len(await self.list(team_id=team_id, project_id=project_id))

    async def get(self, work_item_id: UUID) -> WorkItem | None:
        return self._items.get(work_item_id)

    async def get_by_external_id(self, external_id: str) -> WorkItem | None:
        return next(
            (i for i in self._items.values() if i.external_id == external_id), None
        )


class InMemoryEventRepository:
    """Also counts lookup calls so sync tests can assert query batching."""

    def __init__(self, events: list[Event] | None = None) -> None:
        self._events: dict[UUID, Event] = {e.id: e for e in events or []}
        self.single_lookup_calls = 0
        self.batch_lookup_calls = 0

    async def add(self, event: Event) -> None:
        self._events[event.id] = event

    async def list_for_work_item(self, work_item_id: UUID) -> list[Event]:
        return sorted(
            (e for e in self._events.values() if e.work_item_id == work_item_id),
            key=lambda e: e.occurred_at,
        )

    async def list_for_work_items(self, work_item_ids: list[UUID]) -> list[Event]:
        wanted = set(work_item_ids)
        return sorted(
            (e for e in self._events.values() if e.work_item_id in wanted),
            key=lambda e: e.occurred_at,
        )

    async def get_by_external_id(self, external_id: str) -> Event | None:
        self.single_lookup_calls += 1
        return next(
            (e for e in self._events.values() if e.external_id == external_id), None
        )

    async def existing_external_ids(self, external_ids: list[str]) -> set[str]:
        self.batch_lookup_calls += 1
        wanted = set(external_ids)
        return {
            e.external_id
            for e in self._events.values()
            if e.external_id is not None and e.external_id in wanted
        }


class FakeDataSource:
    """Configurable DeliveryDataSource returning canned snapshots."""

    def __init__(
        self,
        teams: list[SourceTeam] | None = None,
        projects: list[SourceProject] | None = None,
        work_items: list[SourceWorkItem] | None = None,
    ) -> None:
        self.teams = teams or []
        self.projects = projects or []
        self.work_items = work_items or []

    async def fetch_teams(self) -> list[SourceTeam]:
        return self.teams

    async def fetch_projects(self) -> list[SourceProject]:
        return self.projects

    async def fetch_work_items(self) -> list[SourceWorkItem]:
        return self.work_items


class InMemoryMetricSnapshotRepository:
    def __init__(self, snapshots: list[MetricSnapshot] | None = None) -> None:
        self._snapshots: dict[UUID, MetricSnapshot] = {s.id: s for s in snapshots or []}

    async def add(self, snapshot: MetricSnapshot) -> None:
        self._snapshots[snapshot.id] = snapshot

    async def list(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[MetricSnapshot]:
        found = [
            s
            for s in self._snapshots.values()
            if (team_id is None or s.team_id == team_id)
            and (project_id is None or s.project_id == project_id)
        ]
        return sorted(found, key=lambda s: s.captured_on)

    async def exists_on(
        self,
        captured_on: date,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        scoped = await self.list(team_id=team_id, project_id=project_id)
        return any(s.captured_on == captured_on for s in scoped)


class InMemoryAdviceFeedbackRepository:
    def __init__(self, feedback: list[AdviceFeedback] | None = None) -> None:
        self._feedback: dict[UUID, AdviceFeedback] = {f.id: f for f in feedback or []}

    async def add(self, feedback: AdviceFeedback) -> None:
        self._feedback[feedback.id] = feedback

    async def list_for_persona(
        self, persona: Persona, *, since: datetime | None = None
    ) -> list[AdviceFeedback]:
        found = [
            f
            for f in self._feedback.values()
            if f.persona is persona and (since is None or f.created_at > since)
        ]
        return sorted(found, key=lambda f: f.created_at)


class InMemoryPersonaGuidanceRepository:
    def __init__(self, guidance: list[PersonaGuidance] | None = None) -> None:
        self._guidance: dict[UUID, PersonaGuidance] = {g.id: g for g in guidance or []}

    async def add(self, guidance: PersonaGuidance) -> None:
        self._guidance[guidance.id] = guidance

    async def latest(self, persona: Persona) -> PersonaGuidance | None:
        versions = await self.list_versions(persona)
        return versions[0] if versions else None

    async def list_versions(self, persona: Persona) -> list[PersonaGuidance]:
        found = [g for g in self._guidance.values() if g.persona is persona]
        return sorted(found, key=lambda g: g.version, reverse=True)

    async def get_version(self, persona: Persona, version: int) -> PersonaGuidance | None:
        return next(
            (
                g
                for g in self._guidance.values()
                if g.persona is persona and g.version == version
            ),
            None,
        )


class InMemoryForecastSnapshotRepository:
    def __init__(self, snapshots: list[ForecastSnapshot] | None = None) -> None:
        self._snapshots: dict[UUID, ForecastSnapshot] = {
            s.id: s for s in snapshots or []
        }

    async def add(self, snapshot: ForecastSnapshot) -> None:
        self._snapshots[snapshot.id] = snapshot

    async def list(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[ForecastSnapshot]:
        found = [
            s
            for s in self._snapshots.values()
            if (team_id is None or s.team_id == team_id)
            and (project_id is None or s.project_id == project_id)
        ]
        return sorted(found, key=lambda s: s.captured_on)

    async def exists_on(
        self,
        captured_on: date,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        scoped = await self.list(team_id=team_id, project_id=project_id)
        return any(s.captured_on == captured_on for s in scoped)
