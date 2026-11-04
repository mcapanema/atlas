from dataclasses import replace
from typing import Protocol

from app.domain.codebases.entities import Deployment, PullRequest
from app.domain.incidents.entities import ServiceIncident


class _Upsertable[T: (PullRequest, Deployment, ServiceIncident)](Protocol):
    async def get_by_external_ids(self, external_ids: list[str]) -> dict[str, T]: ...

    async def add(self, row: T, /) -> None: ...

    async def update(self, row: T, /) -> None: ...


async def upsert_by_external_id[T: (PullRequest, Deployment, ServiceIncident)](
    repository: _Upsertable[T], rows: list[T]
) -> int:
    """Add new rows and update changed ones (matched by external_id); returns rows written.

    A row the source returned twice (updated mid-pagination) is written once,
    as its first, newest copy.
    """
    rows = list({row.external_id: row for row in reversed(rows)}.values())[::-1]
    stored = await repository.get_by_external_ids([r.external_id for r in rows])
    written = 0
    for row in rows:
        existing = stored.get(row.external_id)
        if existing is None:
            await repository.add(row)
        else:
            row = replace(row, id=existing.id)
            if row == existing:
                continue
            await repository.update(row)
        written += 1
    return written
