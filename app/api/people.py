from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import PeopleServiceDep
from app.api.schemas import PersonRead, PersonWrite
from app.application.people.service import UnknownPersonError

router = APIRouter(prefix="/api/people", tags=["people"])


@router.get("", response_model=list[PersonRead])
async def list_people(
    service: PeopleServiceDep, organization_id: UUID | None = None
) -> list[PersonRead]:
    return [PersonRead.model_validate(p) for p in await service.list(organization_id)]


@router.patch("/{person_id}", response_model=PersonRead)
async def set_display_name(
    person_id: UUID, payload: PersonWrite, service: PeopleServiceDep
) -> PersonRead:
    try:
        person = await service.set_display_name(person_id, payload.display_name)
    except UnknownPersonError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PersonRead.model_validate(person)
