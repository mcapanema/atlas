"""Checks a credential with its provider before it is stored.

A credential the provider rejects raises `CredentialCheckError` (answered 422);
an outage (network, 5xx, 429) propagates as `DataSourceError`/`AdvisorError`
(answered 502).
"""

import httpx

from app.domain.credentials.entities import Credential, Integration
from app.domain.credentials.port import CredentialCheckError
from app.domain.sync.port import DataSourceError
from app.infrastructure.ai.key_check import (
    check_openrouter_key,
    check_openrouter_model,
    is_rejection,
)
from app.infrastructure.connectors.github.client import GitHubGraphQLClient
from app.infrastructure.connectors.linear.client import LinearGraphQLClient
from app.infrastructure.connectors.linear.datasource import LinearDataSource

_GITHUB_OWNER_QUERY = "query($owner: String!) { repositoryOwner(login: $owner) { login } }"


class ProviderCredentialVerifier:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def verify(self, credential: Credential) -> None:
        try:
            await self._check(credential)
        except DataSourceError as exc:
            if is_rejection(exc.status):
                raise CredentialCheckError(
                    f"Could not verify the {credential.integration.label} credentials: {exc}"
                ) from exc
            raise

    async def _check(self, credential: Credential) -> None:
        secret = credential.secret
        match credential.integration:
            case Integration.LINEAR:
                client = LinearGraphQLClient(secret, transport=self._transport)
                await LinearDataSource(client).fetch_organization_name()
            case Integration.GITHUB:
                await self._check_github(secret, credential.owner)
            case Integration.OPENROUTER:
                await check_openrouter_key(secret, self._transport)
                # The entity requires a model for OpenRouter; "" is only for the type checker.
                await check_openrouter_model(credential.model or "", self._transport)

    async def _check_github(self, token: str, owner: str | None) -> None:
        client = GitHubGraphQLClient(token, transport=self._transport)
        data = await client.execute(_GITHUB_OWNER_QUERY, {"owner": owner})
        if data.get("repositoryOwner") is None:
            raise CredentialCheckError(
                f"Could not verify the GitHub credentials: owner '{owner}' "
                "was not found or the token can't see it"
            )
