from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.domain.sync.port import DataSourceError
from app.infrastructure.connectors import retry as retry_module
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

    monkeypatch.setattr(retry_module, "_sleep", fake_sleep)
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


async def test_http_error_carries_the_status() -> None:
    with pytest.raises(AcmeError) as caught:
        await _client(lambda r: httpx.Response(401)).execute("{ x }")
    assert caught.value.status == 401


async def test_graphql_errors_payload_carries_the_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "no"}]})

    with pytest.raises(AcmeError) as caught:
        await _client(handler).execute("{ x }")
    assert caught.value.status == 200


async def test_network_failure_has_no_status() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.UnsupportedProtocol("boom")  # not retried

    with pytest.raises(AcmeError) as caught:
        await _client(fail).execute("{ x }")
    assert caught.value.status is None


_NO_ACCESS = "Resource not accessible by personal access token"


def _forbidden(path: list[str | int]) -> dict[str, Any]:
    return {"type": "FORBIDDEN", "path": path, "message": _NO_ACCESS}


async def _graphql_error_message(errors: list[Any], data: Any = None) -> str:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": errors, "data": data})

    with pytest.raises(AcmeError) as caught:
        await _client(handler).execute("{ a }")
    return str(caught.value)


async def test_graphql_errors_are_collapsed_by_wildcard_path() -> None:
    errors = [
        _forbidden(["node", "pullRequests", "nodes", 11, "mergeCommit"]),
        _forbidden(["node", "pullRequests", "nodes", 12, "mergeCommit"]),
        _forbidden(["node", "pullRequests", "nodes", 0, "commits", "nodes", 0]),
    ]

    # Partial data with errors still fails: no half-mapped records.
    message = await _graphql_error_message(errors, data={"node": {}})

    assert message == (
        "Acme GraphQL errors: "
        f"FORBIDDEN at node.pullRequests.nodes.*.mergeCommit: {_NO_ACCESS}; "
        f"FORBIDDEN at node.pullRequests.nodes.*.commits.nodes.*: {_NO_ACCESS}"
        " (3 errors)"
    )


async def test_graphql_error_without_type_or_path_is_its_message() -> None:
    message = await _graphql_error_message([{"message": "boom"}, "raw"])

    assert message == "Acme GraphQL errors: boom; raw"


async def test_graphql_errors_list_at_most_five_kinds() -> None:
    message = await _graphql_error_message([{"message": f"m{i}"} for i in range(7)])

    assert message == "Acme GraphQL errors: m0; m1; m2; m3; m4; …and 2 more"
