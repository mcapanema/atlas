import json

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_credential_verifier
from app.domain.credentials.port import CredentialCheckError
from app.domain.sync.port import DataSourceError
from app.infrastructure.connectors.github.client import GITHUB_GRAPHQL_URL
from app.infrastructure.credential_checks import ProviderCredentialVerifier
from tests.fakes import FakeCredentialVerifier


@pytest.fixture
def verifier(test_app: FastAPI) -> FakeCredentialVerifier:
    fake = FakeCredentialVerifier()
    test_app.dependency_overrides[get_credential_verifier] = lambda: fake
    return fake


async def test_put_linear_credentials_strips_and_reports_hint(
    client: AsyncClient, verifier: FakeCredentialVerifier
) -> None:
    response = await client.put(
        "/api/connectors/linear/credentials", json={"api_key": "  lin_api_abcd1234\n"}
    )

    assert response.status_code == 200
    assert response.json() == {"configured": True, "hint": "…1234", "running": None}
    assert verifier.verified[0].secret == "lin_api_abcd1234"
    status = await client.get("/api/connectors/linear")
    assert status.json()["hint"] == "…1234"
    assert "lin_api_abcd1234" not in status.text


async def test_put_rejected_key_answers_422_and_stores_nothing(
    client: AsyncClient, verifier: FakeCredentialVerifier
) -> None:
    verifier.error = CredentialCheckError(
        "Could not verify the Linear credentials: Linear API returned HTTP 400"
    )

    response = await client.put("/api/connectors/linear/credentials", json={"api_key": "bad"})

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "Could not verify the Linear credentials: Linear API returned HTTP 400"
    )
    assert (await client.get("/api/connectors/linear")).json()["configured"] is False


async def test_put_during_provider_outage_answers_502_and_stores_nothing(
    client: AsyncClient, verifier: FakeCredentialVerifier
) -> None:
    verifier.error = DataSourceError("Linear API returned HTTP 503", status=503)

    response = await client.put("/api/connectors/linear/credentials", json={"api_key": "lin_api_x"})

    assert response.status_code == 502
    assert (await client.get("/api/connectors/linear")).json()["configured"] is False


async def test_rejected_body_never_echoes_the_secret(
    client: AsyncClient, verifier: FakeCredentialVerifier
) -> None:
    secret = "s3cret" * 100  # 600 chars, over max_length

    response = await client.put("/api/connectors/linear/credentials", json={"api_key": secret})

    assert response.status_code == 422
    assert "s3cret" not in response.text


async def test_delete_removes_and_is_idempotent(
    client: AsyncClient, verifier: FakeCredentialVerifier
) -> None:
    await client.put("/api/connectors/linear/credentials", json={"api_key": "lin_api_x"})

    for _ in range(2):
        response = await client.delete("/api/connectors/linear/credentials")
        assert response.status_code == 200
        assert response.json()["configured"] is False


async def test_github_credentials_need_an_owner(
    client: AsyncClient, verifier: FakeCredentialVerifier
) -> None:
    missing = await client.put("/api/connectors/github/credentials", json={"token": "ghp_x"})
    assert missing.status_code == 422

    response = await client.put(
        "/api/connectors/github/credentials",
        json={"token": "ghp_0000000abcd", "owner": " acme "},
    )

    assert response.json() == {
        "configured": True,
        "owner": "acme",
        "hint": "…abcd",
        "running": None,
    }
    deleted = await client.delete("/api/connectors/github/credentials")
    assert deleted.json() == {"configured": False, "owner": None, "hint": None, "running": None}


async def test_openrouter_status_defaults_the_model(
    client: AsyncClient, verifier: FakeCredentialVerifier
) -> None:
    unconfigured = await client.get("/api/connectors/openrouter")
    assert unconfigured.json() == {
        "configured": False,
        "model": "anthropic/claude-sonnet-5",
        "hint": None,
    }

    await client.put(
        "/api/connectors/openrouter/credentials",
        json={"api_key": "sk-or-v1-xxxx9876", "model": "openai/gpt-5"},
    )

    assert (await client.get("/api/connectors/openrouter")).json() == {
        "configured": True,
        "model": "openai/gpt-5",
        "hint": "…9876",
    }
    assert (await client.get("/api/recommendations/status")).json() == {"configured": True}
    deleted = await client.delete("/api/connectors/openrouter/credentials")
    assert deleted.json()["configured"] is False


async def test_github_owner_changes_without_the_token(
    client: AsyncClient, verifier: FakeCredentialVerifier
) -> None:
    await client.put(
        "/api/connectors/github/credentials", json={"token": "ghp_secret_abcd", "owner": "acme"}
    )

    response = await client.put("/api/connectors/github/credentials", json={"owner": "globex"})

    assert response.status_code == 200
    assert response.json() == {
        "configured": True,
        "owner": "globex",
        "hint": "…abcd",
        "running": None,
    }
    assert verifier.verified[-1].secret == "ghp_secret_abcd"


async def test_openrouter_model_changes_without_the_key(
    client: AsyncClient, verifier: FakeCredentialVerifier
) -> None:
    await client.put(
        "/api/connectors/openrouter/credentials", json={"api_key": "sk-or-v1-xxxx9876"}
    )

    response = await client.put(
        "/api/connectors/openrouter/credentials", json={"model": "openai/gpt-5"}
    )

    assert response.json() == {"configured": True, "model": "openai/gpt-5", "hint": "…9876"}


async def test_kept_github_token_rejected_for_a_new_owner_keeps_the_old_one(
    client: AsyncClient, test_app: FastAPI
) -> None:
    # The real verifier against a fake GitHub that only knows the owner "acme".
    def answer(request: httpx.Request) -> httpx.Response:
        assert request.url == GITHUB_GRAPHQL_URL
        assert request.headers["Authorization"] == "Bearer ghp_secret_abcd"
        owner = json.loads(request.content)["variables"]["owner"]
        found = {"login": owner} if owner == "acme" else None
        return httpx.Response(200, json={"data": {"repositoryOwner": found}})

    verifier = ProviderCredentialVerifier(httpx.MockTransport(answer))
    test_app.dependency_overrides[get_credential_verifier] = lambda: verifier
    stored = await client.put(
        "/api/connectors/github/credentials", json={"token": "ghp_secret_abcd", "owner": "acme"}
    )
    assert stored.status_code == 200

    response = await client.put("/api/connectors/github/credentials", json={"owner": "globex"})

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Could not verify the GitHub credentials: owner 'globex' "
        "was not found or the token can't see it"
    )
    assert "ghp_secret_abcd" not in response.text
    status = (await client.get("/api/connectors/github")).json()
    assert (status["owner"], status["hint"]) == ("acme", "…abcd")


async def test_omitted_secret_with_nothing_stored_answers_422(
    client: AsyncClient, verifier: FakeCredentialVerifier
) -> None:
    response = await client.put("/api/connectors/github/credentials", json={"owner": "acme"})

    assert response.status_code == 422
    assert response.json()["detail"] == "No GitHub key is stored yet; enter one"
    assert verifier.verified == []


async def test_linear_key_is_still_required(
    client: AsyncClient, verifier: FakeCredentialVerifier
) -> None:
    response = await client.put("/api/connectors/linear/credentials", json={})

    assert response.status_code == 422


async def test_put_datadog_credentials_stores_and_reports_status(
    client: AsyncClient, verifier: FakeCredentialVerifier
) -> None:
    response = await client.put(
        "/api/connectors/datadog/credentials",
        json={
            "api_key": "dd-api-key-abcd1234",
            "application_key": "dd-app-secret",
            "site": "datadoghq.eu",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "configured": True,
        "site": "datadoghq.eu",
        "hint": "…1234",
        "running": None,
    }
    assert "dd-app-secret" not in response.text
    assert verifier.verified[0].application_key == "dd-app-secret"
    status = await client.get("/api/connectors/datadog")
    assert status.json()["site"] == "datadoghq.eu"
    assert "dd-app-secret" not in status.text
    deleted = await client.delete("/api/connectors/datadog/credentials")
    assert deleted.json() == {"configured": False, "site": None, "hint": None, "running": None}


async def test_put_datadog_credentials_rejects_unknown_site(
    client: AsyncClient, verifier: FakeCredentialVerifier
) -> None:
    response = await client.put(
        "/api/connectors/datadog/credentials",
        json={"api_key": "dd", "application_key": "app-secret", "site": "example.com"},
    )

    assert response.status_code == 422
    assert "app-secret" not in response.text
    assert verifier.verified == []


async def test_put_datadog_credentials_needs_both_keys(
    client: AsyncClient, verifier: FakeCredentialVerifier
) -> None:
    response = await client.put(
        "/api/connectors/datadog/credentials", json={"api_key": "dd", "site": "datadoghq.com"}
    )

    assert response.status_code == 422
