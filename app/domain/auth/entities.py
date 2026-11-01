import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from app.domain._time import require_aware, utcnow

MIN_PASSWORD_LENGTH = 12
# The max bounds the scrypt work a single request can cause.
MAX_PASSWORD_LENGTH = 128
SESSION_LIFETIME = timedelta(days=14)

_MAX_EMAIL_LENGTH = 254
_MAX_NAME_LENGTH = 255
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > _MAX_EMAIL_LENGTH:
        raise ValueError(f"email must be at most {_MAX_EMAIL_LENGTH} characters")
    if not _EMAIL_PATTERN.match(email):
        raise ValueError("email is not a valid address")
    return email


def require_valid_password(value: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(value) <= MAX_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters"
        )


@dataclass
class User:
    """A person who signs in. `password_hash` is None when no password can be used."""

    email: str
    name: str
    password_hash: str | None
    is_admin: bool = False
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        self.email = normalize_email(self.email)
        stripped = self.name.strip()
        if not stripped or len(stripped) > _MAX_NAME_LENGTH:
            raise ValueError(f"User name must be 1 to {_MAX_NAME_LENGTH} characters")
        self.name = stripped
        require_aware("User", created_at=self.created_at)


@dataclass
class AuthSession:
    """A signed-in browser session. Only the hash of its token is stored."""

    token_hash: str
    user_id: UUID
    expires_at: datetime
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        require_aware("AuthSession", expires_at=self.expires_at, created_at=self.created_at)

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at
