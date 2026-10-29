from collections.abc import Callable

import httpx
import pytest

from app.domain.sync.port import DataSourceError
from app.infrastructure.connectors import graphql as graphql_module
from app.infrastructure.connectors.graphql import GraphQLClient


class AcmeError(DataSourceError):
    pass


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> GraphQLClient:
    return GraphQLClient(
        "https://acme.test/graphql",
        {"Authorization": "Bearer t"},
        vendor="Acme",
        error=AcmeError,
        transport=httpx.MockTransport(handler),
    )


@pytest.fixture
def recorded_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(graphql_module, "_sleep", fake_sleep)
    return sleeps


async def test_execute_retries_403_with_retry_after(recorded_sleeps: list[float]) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(403, headers={"Retry-After": "5"}, json={})
        return httpx.Response(200, json={"data": {"ok": True}})

    assert await _client(handler).execute("{ a }") == {"ok": True}
    assert recorded_sleeps == [5.0]


async def test_execute_fails_fast_on_403_without_retry_after(
    recorded_sleeps: list[float],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={})

    with pytest.raises(AcmeError, match=r"^Acme API returned HTTP 403$"):
        await _client(handler).execute("{ a }")

    assert recorded_sleeps == []


async def test_execute_raises_the_given_error_type_on_graphql_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "boom"}], "data": None})

    with pytest.raises(AcmeError, match=r"Acme GraphQL errors: .*boom"):
        await _client(handler).execute("{ a }")
