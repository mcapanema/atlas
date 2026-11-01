from typing import Protocol

from app.domain.credentials.entities import Credential, Integration


class CredentialRepository(Protocol):
    """Port for stored connector credentials, one per integration. Implemented in Infrastructure."""

    async def get(self, integration: Integration) -> Credential | None: ...

    async def save(self, credential: Credential) -> None:
        """Insert, or replace the existing credential of that integration."""
        ...

    async def delete(self, integration: Integration) -> None:
        """No-op when absent."""
        ...
