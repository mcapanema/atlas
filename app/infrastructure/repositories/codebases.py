from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Integer, String, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.codebases.entities import Codebase, Deployment, DeploymentStatus, PullRequest
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UTCDateTime
from app.infrastructure.repositories.batching import chunked


class CodebaseModel(Base):
    __tablename__ = "codebases"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), nullable=False, index=True
    )
    team_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("teams.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    production_environment: Mapped[str] = mapped_column(
        String(255), nullable=False, default="production", server_default="production"
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    def to_domain(self) -> Codebase:
        return Codebase(
            id=self.id,
            organization_id=self.organization_id,
            team_id=self.team_id,
            name=self.name,
            external_id=self.external_id,
            url=self.url,
            production_environment=self.production_environment,
            last_synced_at=self.last_synced_at,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, codebase: Codebase) -> "CodebaseModel":
        return cls(
            id=codebase.id,
            organization_id=codebase.organization_id,
            team_id=codebase.team_id,
            name=codebase.name,
            external_id=codebase.external_id,
            url=codebase.url,
            production_environment=codebase.production_environment,
            last_synced_at=codebase.last_synced_at,
            created_at=codebase.created_at,
        )


class PullRequestModel(Base):
    __tablename__ = "pull_requests"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    codebase_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("codebases.id"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    first_commit_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    merged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    merge_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    work_item_keys: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )

    def to_domain(self) -> PullRequest:
        return PullRequest(
            id=self.id,
            codebase_id=self.codebase_id,
            external_id=self.external_id,
            number=self.number,
            title=self.title,
            url=self.url,
            opened_at=self.opened_at,
            first_commit_at=self.first_commit_at,
            merged_at=self.merged_at,
            closed_at=self.closed_at,
            merge_commit_sha=self.merge_commit_sha,
            work_item_keys=tuple(self.work_item_keys),
        )

    @classmethod
    def from_domain(cls, pr: PullRequest) -> "PullRequestModel":
        return cls(
            id=pr.id,
            codebase_id=pr.codebase_id,
            external_id=pr.external_id,
            number=pr.number,
            title=pr.title,
            url=pr.url,
            opened_at=pr.opened_at,
            first_commit_at=pr.first_commit_at,
            merged_at=pr.merged_at,
            closed_at=pr.closed_at,
            merge_commit_sha=pr.merge_commit_sha,
            work_item_keys=list(pr.work_item_keys),
        )


class DeploymentModel(Base):
    __tablename__ = "deployments"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    codebase_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("codebases.id"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    environment: Mapped[str] = mapped_column(String(255), nullable=False)
    sha: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    def to_domain(self) -> Deployment:
        return Deployment(
            id=self.id,
            codebase_id=self.codebase_id,
            external_id=self.external_id,
            environment=self.environment,
            sha=self.sha,
            started_at=self.started_at,
            status=DeploymentStatus(self.status),
            finished_at=self.finished_at,
        )

    @classmethod
    def from_domain(cls, deployment: Deployment) -> "DeploymentModel":
        return cls(
            id=deployment.id,
            codebase_id=deployment.codebase_id,
            external_id=deployment.external_id,
            environment=deployment.environment,
            sha=deployment.sha,
            started_at=deployment.started_at,
            status=deployment.status.value,
            finished_at=deployment.finished_at,
        )


class SqlAlchemyCodebaseRepository:
    """SQLAlchemy adapter for the CodebaseRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, codebase: Codebase) -> None:
        self._session.add(CodebaseModel.from_domain(codebase))
        await self._session.flush()

    async def update(self, codebase: Codebase) -> None:
        await self._session.merge(CodebaseModel.from_domain(codebase))
        await self._session.flush()

    async def get(self, codebase_id: UUID) -> Codebase | None:
        model = await self._session.get(CodebaseModel, codebase_id)
        return model.to_domain() if model is not None else None

    async def get_by_external_ids(self, external_ids: list[str]) -> dict[str, Codebase]:
        found: dict[str, Codebase] = {}
        for chunk in chunked(external_ids):
            result = await self._session.execute(
                select(CodebaseModel).where(CodebaseModel.external_id.in_(chunk))
            )
            for model in result.scalars():
                found[model.external_id] = model.to_domain()
        return found

    async def list(self, organization_id: UUID) -> list[Codebase]:
        result = await self._session.execute(
            select(CodebaseModel)
            .where(CodebaseModel.organization_id == organization_id)
            .order_by(CodebaseModel.created_at)
        )
        return [model.to_domain() for model in result.scalars()]


class SqlAlchemyPullRequestRepository:
    """SQLAlchemy adapter for the PullRequestRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, pull_request: PullRequest) -> None:
        self._session.add(PullRequestModel.from_domain(pull_request))
        await self._session.flush()

    async def update(self, pull_request: PullRequest) -> None:
        await self._session.merge(PullRequestModel.from_domain(pull_request))
        await self._session.flush()

    async def get_by_external_ids(self, external_ids: list[str]) -> dict[str, PullRequest]:
        found: dict[str, PullRequest] = {}
        for chunk in chunked(external_ids):
            result = await self._session.execute(
                select(PullRequestModel).where(PullRequestModel.external_id.in_(chunk))
            )
            for model in result.scalars():
                found[model.external_id] = model.to_domain()
        return found

    async def list_for_codebases(self, codebase_ids: list[UUID]) -> list[PullRequest]:
        pulls: list[PullRequest] = []
        for chunk in chunked(codebase_ids):
            result = await self._session.execute(
                select(PullRequestModel).where(PullRequestModel.codebase_id.in_(chunk))
            )
            pulls.extend(model.to_domain() for model in result.scalars())
        pulls.sort(key=lambda pr: pr.opened_at)
        return pulls

    async def count_by_codebase(self, codebase_ids: list[UUID]) -> dict[UUID, int]:
        counts: dict[UUID, int] = {}
        for chunk in chunked(codebase_ids):
            result = await self._session.execute(
                select(PullRequestModel.codebase_id, func.count())
                .where(PullRequestModel.codebase_id.in_(chunk))
                .group_by(PullRequestModel.codebase_id)
            )
            counts.update(dict(result.all()))
        return counts


class SqlAlchemyDeploymentRepository:
    """SQLAlchemy adapter for the DeploymentRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, deployment: Deployment) -> None:
        self._session.add(DeploymentModel.from_domain(deployment))
        await self._session.flush()

    async def update(self, deployment: Deployment) -> None:
        await self._session.merge(DeploymentModel.from_domain(deployment))
        await self._session.flush()

    async def get_by_external_ids(self, external_ids: list[str]) -> dict[str, Deployment]:
        found: dict[str, Deployment] = {}
        for chunk in chunked(external_ids):
            result = await self._session.execute(
                select(DeploymentModel).where(DeploymentModel.external_id.in_(chunk))
            )
            for model in result.scalars():
                found[model.external_id] = model.to_domain()
        return found

    async def list_for_codebases(self, codebase_ids: list[UUID]) -> list[Deployment]:
        deployments: list[Deployment] = []
        for chunk in chunked(codebase_ids):
            result = await self._session.execute(
                select(DeploymentModel).where(DeploymentModel.codebase_id.in_(chunk))
            )
            deployments.extend(model.to_domain() for model in result.scalars())
        deployments.sort(key=lambda d: d.started_at)
        return deployments

    async def count_by_codebase(self, codebase_ids: list[UUID]) -> dict[UUID, int]:
        counts: dict[UUID, int] = {}
        for chunk in chunked(codebase_ids):
            result = await self._session.execute(
                select(DeploymentModel.codebase_id, func.count())
                .where(DeploymentModel.codebase_id.in_(chunk))
                .group_by(DeploymentModel.codebase_id)
            )
            counts.update(dict(result.all()))
        return counts

    async def oldest_pending_started_at(
        self, codebase_id: UUID, *, since: datetime
    ) -> datetime | None:
        result = await self._session.execute(
            select(func.min(DeploymentModel.started_at)).where(
                DeploymentModel.codebase_id == codebase_id,
                DeploymentModel.status == DeploymentStatus.PENDING.value,
                DeploymentModel.started_at >= since,
            )
        )
        return result.scalar_one()
