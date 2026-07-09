from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.work_items.entities import WorkItemType


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime


class TeamCreate(BaseModel):
    organization_id: UUID
    name: str = Field(min_length=1, max_length=255)
    external_id: str | None = None


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    external_id: str | None
    created_at: datetime


class ProjectCreate(BaseModel):
    team_id: UUID
    name: str = Field(min_length=1, max_length=255)
    external_id: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    name: str
    external_id: str | None
    created_at: datetime


class WorkItemCreate(BaseModel):
    team_id: UUID
    title: str = Field(min_length=1, max_length=1024)
    type: WorkItemType = WorkItemType.TASK
    state: str = Field(default="backlog", min_length=1, max_length=255)
    project_id: UUID | None = None
    external_id: str | None = None


class WorkItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    project_id: UUID | None
    title: str
    type: WorkItemType
    state: str
    external_id: str | None
    created_at: datetime
