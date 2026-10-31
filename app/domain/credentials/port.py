from typing import Protocol

from app.domain.credentials.entities import Credential


class CredentialCheckError(ValueError):
    """The provider rejected the credential. A ValueError so the API answers 422 with the reason."""


class CredentialVerifier(Protocol):
    """Port that checks a credential against its provider. Implemented in Infrastructure."""

    async def verify(self, credential: Credential) -> None:
        """Raise CredentialCheckError when the provider rejects the credential."""
        ...
