import hashlib
import secrets


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session_token() -> tuple[str, str]:
    """Return `(token, token_hash)`: the token goes to the browser, the hash to the database."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


MCP_TOKEN_PREFIX = "atlas_mcp_"  # noqa: S105 — a public prefix, not a secret


def new_mcp_token() -> tuple[str, str]:
    """Return `(secret, hash)`: the secret is shown once, the hash is stored."""
    secret = MCP_TOKEN_PREFIX + secrets.token_urlsafe(32)
    return secret, hash_token(secret)
