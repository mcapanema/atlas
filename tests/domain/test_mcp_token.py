from datetime import timedelta
from uuid import uuid4

import pytest

from app.domain._time import utcnow
from app.domain.auth.entities import LAST_USED_RESOLUTION, McpAccess, McpToken
from app.domain.auth.tokens import hash_token, new_mcp_token


def test_a_token_name_is_stripped_and_bounded() -> None:
    assert (
        McpToken(uuid4(), "  Claude Code ", McpAccess.READ, "h" * 64, "abcd").name == "Claude Code"
    )
    with pytest.raises(ValueError, match="1 to 100"):
        McpToken(uuid4(), "   ", McpAccess.READ, "h" * 64, "abcd")
    with pytest.raises(ValueError, match="1 to 100"):
        McpToken(uuid4(), "x" * 101, McpAccess.READ, "h" * 64, "abcd")


def test_needs_touch_once_per_resolution() -> None:
    now = utcnow()
    token = McpToken(uuid4(), "n", McpAccess.READ, "h" * 64, "abcd")
    assert token.needs_touch(now)  # never used
    token.last_used_at = now - timedelta(minutes=4)
    assert not token.needs_touch(now)
    token.last_used_at = now - LAST_USED_RESOLUTION
    assert token.needs_touch(now)


def test_new_mcp_token_returns_a_prefixed_secret_and_its_hash() -> None:
    secret, digest = new_mcp_token()
    assert secret.startswith("atlas_mcp_")
    assert len(secret) >= 50
    assert digest == hash_token(secret)
