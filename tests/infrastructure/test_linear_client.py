import json
from collections.abc import Callable

import httpx
import pytest

from app.domain.sync.port import DataSourceError
from app.infrastructure.connectors.linear import client as client_module
from app.infrastructure.connectors.linear.client import LinearAPIError, LinearGraphQLClient


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> LinearGraphQLClient:
    return LinearGraphQLClient("lin_api_test", transport=httpx.MockTransport(handler))


async def test_execute_sends_raw_api_key_and_returns_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "lin_api_test"  # no "Bearer" prefix
        body = json.loads(request.content)
        assert body["query"] == "{ viewer { id } }"
        assert body["variables"] == {}
        return httpx.Response(200, json={"data": {"viewer": {"id": "u1"}}})

    data = await _client(handler).execute("{ viewer { id } }")

    assert data == {"viewer": {"id": "u1"}}


async def test_execute_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    with pytest.raises(LinearAPIError, match="401"):
        await _client(handler).execute("{ viewer { id } }")


async def test_execute_raises_on_graphql_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "bad query"}], "data": None})

    with pytest.raises(LinearAPIError, match="bad query"):
        await _client(handler).execute("{ nope }")


def test_linear_api_error_is_a_data_source_error() -> None:
    # The 502 handler in create_app() catches DataSourceError; Linear failures
    # must be members of that family to reach it.
    assert issubclass(LinearAPIError, DataSourceError)


@pytest.fixture
def recorded_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(client_module, "_sleep", fake_sleep)
    return sleeps


async def test_execute_retries_429_honoring_retry_after(recorded_sleeps: list[float]) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(429, headers={"Retry-After": "7"}, json={})
        return httpx.Response(200, json={"data": {"viewer": {"id": "u1"}}})

    data = await _client(handler).execute("{ viewer { id } }")

    assert data == {"viewer": {"id": "u1"}}
    assert calls == 3
    assert recorded_sleeps == [7.0, 7.0]


async def test_execute_retries_5xx_with_exponential_backoff(
    recorded_sleeps: list[float],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={})  # no Retry-After header
        return httpx.Response(200, json={"data": {"ok": True}})

    data = await _client(handler).execute("{ viewer { id } }")

    assert data == {"ok": True}
    assert recorded_sleeps == [1.0]  # 2 ** (attempt - 1)


async def test_execute_gives_up_after_max_attempts(recorded_sleeps: list[float]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={})

    with pytest.raises(LinearAPIError, match="429"):
        await _client(handler).execute("{ viewer { id } }")

    assert recorded_sleeps == [1.0, 2.0]  # 3 attempts total, 2 sleeps


async def test_execute_does_not_retry_4xx_other_than_429() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    with pytest.raises(LinearAPIError, match="401"):
        await _client(handler).execute("{ viewer { id } }")

    assert calls == 1


async def test_execute_wraps_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(LinearAPIError, match="request failed"):
        await _client(handler).execute("{ viewer { id } }")
