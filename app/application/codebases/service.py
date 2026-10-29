import logging
from dataclasses import dataclass, replace
from uuid import UUID

from app.domain.codebases.entities import Codebase
from app.domain.codebases.repository import (
    CodebaseRepository,
    DeploymentRepository,
    PullRequestRepository,
)
from app.domain.teams.repository import TeamRepository

logger = logging.getLogger(__name__)


class UnknownCodebaseError(Exception):
    """A codebase that doesn't exist was addressed (404, not 422)."""


@dataclass(frozen=True)
class CodebaseOverview:
    """A codebase with how many pull requests and deployments are stored for it."""

    codebase: Codebase
    pull_requests: int
    deployments: int


class CodebaseService:
    """Lists codebases with their counts and maps them to teams."""

    def __init__(
        self,
        codebases: CodebaseRepository,
        teams: TeamRepository,
        pull_requests: PullRequestRepository,
        deployments: DeploymentRepository,
    ) -> None:
        self._codebases = codebases
        self._teams = teams
        self._pull_requests = pull_requests
        self._deployments = deployments

    async def list(self, organization_id: UUID) -> list[CodebaseOverview]:
        """The organization's codebases by name, each with its stored counts."""
        codebases = sorted(await self._codebases.list(organization_id), key=lambda c: c.name)
        ids = [c.id for c in codebases]
        pull_requests = await self._pull_requests.count_by_codebase(ids)
        deployments = await self._deployments.count_by_codebase(ids)
        return [
            CodebaseOverview(c, pull_requests.get(c.id, 0), deployments.get(c.id, 0))
            for c in codebases
        ]

    async def update(
        self, codebase_id: UUID, *, team_id: UUID | None, production_environment: str
    ) -> Codebase:
        """Map a codebase to a team (None unmaps it) and set its production environment."""
        codebase = await self._codebases.get(codebase_id)
        if codebase is None:
            raise UnknownCodebaseError(f"Codebase {codebase_id} does not exist")
        if team_id is not None:
            team = await self._teams.get(team_id)
            if team is None or team.organization_id != codebase.organization_id:
                # ValueError on purpose: the global handler answers 422.
                raise ValueError(f"Team {team_id} does not exist in this organization")
        # Rebuilt through the constructor so the entity invariants run.
        updated = replace(codebase, team_id=team_id, production_environment=production_environment)
        await self._codebases.update(updated)
        logger.info("Codebase %s mapped to team %s", codebase_id, team_id)
        return updated
