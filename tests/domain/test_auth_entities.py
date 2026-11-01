from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.auth.entities import AuthSession, User, require_valid_password


def test_email_is_trimmed_and_lowercased() -> None:
    assert User(email="  Ana@Acme.COM ", name="Ana", password_hash=None).email == "ana@acme.com"


@pytest.mark.parametrize("email", ["", "ana", "ana@acme", "a na@acme.com", "x" * 250 + "@a.co"])
def test_invalid_email_is_rejected(email: str) -> None:
    with pytest.raises(ValueError, match="email"):
        User(email=email, name="Ana", password_hash=None)


def test_name_is_stripped() -> None:
    assert User(email="ana@acme.com", name="  Ana ", password_hash=None).name == "Ana"


@pytest.mark.parametrize("name", ["", "   ", "x" * 256])
def test_blank_or_too_long_name_is_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="name"):
        User(email="ana@acme.com", name=name, password_hash=None)


def test_naive_created_at_is_rejected() -> None:
    naive = datetime(2026, 1, 1)  # noqa: DTZ001 — naive on purpose
    with pytest.raises(ValueError, match="timezone-aware"):
        User(email="ana@acme.com", name="Ana", password_hash=None, created_at=naive)


def test_user_is_not_admin_by_default() -> None:
    assert not User(email="ana@acme.com", name="Ana", password_hash=None).is_admin


@pytest.mark.parametrize("password", ["x" * 11, "x" * 129])
def test_password_length_is_bounded(password: str) -> None:
    with pytest.raises(ValueError, match="12"):
        require_valid_password(password)


@pytest.mark.parametrize("password", ["x" * 12, "x" * 128])
def test_password_at_the_bounds_is_accepted(password: str) -> None:
    require_valid_password(password)


def test_session_expires_at_its_deadline() -> None:
    s = AuthSession(token_hash="h", user_id=uuid4(), expires_at=datetime(2026, 11, 1, tzinfo=UTC))
    assert not s.is_expired(datetime(2026, 10, 31, 23, 59, tzinfo=UTC))
    assert s.is_expired(datetime(2026, 11, 1, tzinfo=UTC))


def test_session_requires_aware_datetimes() -> None:
    naive = datetime(2026, 11, 1)  # noqa: DTZ001 — naive on purpose
    with pytest.raises(ValueError, match="timezone-aware"):
        AuthSession(token_hash="h", user_id=uuid4(), expires_at=naive)
