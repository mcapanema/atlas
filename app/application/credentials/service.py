from app.domain.credentials.entities import Credential, Integration
from app.domain.credentials.port import CredentialVerifier
from app.domain.credentials.repository import CredentialRepository


class CredentialService:
    """Application use cases for connector credentials."""

    def __init__(self, repository: CredentialRepository, verifier: CredentialVerifier) -> None:
        self._repository = repository
        self._verifier = verifier

    async def get(self, integration: Integration) -> Credential | None:
        return await self._repository.get(integration)

    async def save(self, credential: Credential) -> None:
        await self._verifier.verify(credential)
        await self._repository.save(credential)

    async def remove(self, integration: Integration) -> None:
        await self._repository.delete(integration)
