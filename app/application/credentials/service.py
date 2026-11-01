from app.domain.credentials.entities import Credential, Integration
from app.domain.credentials.port import CredentialVerifier
from app.domain.credentials.repository import CredentialRepository


class NoStoredCredentialError(ValueError):
    """A save kept the stored secret, but none is stored."""


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

    async def update(
        self,
        integration: Integration,
        secret: str | None,
        *,
        owner: str | None = None,
        model: str | None = None,
    ) -> None:
        """Save the credential; a None secret keeps the stored one, checked again like a new one."""
        if secret is None:
            stored = await self._repository.get(integration)
            if stored is None:
                raise NoStoredCredentialError(
                    f"No {integration.label} key is stored yet; enter one"
                )
            secret = stored.secret
        await self.save(Credential(integration, secret, owner=owner, model=model))

    async def remove(self, integration: Integration) -> None:
        await self._repository.delete(integration)
