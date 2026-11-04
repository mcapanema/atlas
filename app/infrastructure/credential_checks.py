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
from app.infrastructure.connectors.datadog.client import DatadogClient
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
            case Integration.DATADOG:
                await self._check_datadog(credential)
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

    async def _check_datadog(self, credential: Credential) -> None:
        # The entity requires both fields for Datadog; "" is only for the type checker.
        site = credential.site or ""
        client = DatadogClient(
            credential.secret,
            credential.application_key or "",
            site,
            transport=self._transport,
        )
        try:
            await client.get("/api/v1/validate")
        except DataSourceError as exc:
            if is_rejection(exc.status):
                # A key from another site is rejected the same way as a wrong key.
                raise CredentialCheckError(
                    f"Could not verify the Datadog credentials on {site}: {exc}"
                ) from exc
            raise
        await client.get("/api/v2/catalog/entity", {"filter[kind]": "service", "page[limit]": 1})
