from fastapi import APIRouter, status

from app.api.deps import OrganizationServiceDep
from app.api.schemas import OrganizationCreate, OrganizationRead

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


@router.get("", response_model=list[OrganizationRead])
async def list_organizations(service: OrganizationServiceDep) -> list[OrganizationRead]:
    organizations = await service.list_organizations()
    return [OrganizationRead.model_validate(org) for org in organizations]


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    service: OrganizationServiceDep,
) -> OrganizationRead:
    organization = await service.create_organization(payload.name)
    return OrganizationRead.model_validate(organization)
