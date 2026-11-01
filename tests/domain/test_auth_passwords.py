import pytest

from app.domain.auth.passwords import hash_password, verify_password
from app.domain.auth.tokens import hash_token, new_session_token


def test_hash_verifies_only_the_same_password() -> None:
    stored = hash_password("correct horse battery")
    assert stored.startswith("scrypt$16384$8$1$")
    assert verify_password("correct horse battery", stored)
    assert not verify_password("correct horse batterY", stored)


def test_same_password_hashes_differently() -> None:
    assert hash_password("correct horse battery") != hash_password("correct horse battery")


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "bcrypt$x",
        "scrypt$1$2$3$!!$!!",
        "scrypt$16384$8$1$abc",
        "scrypt$99999999999999999999999$8$1$AAAA$AAAA",
        "scrypt$16384$8$-1$AAAA$AAAA",
    ],
)
def test_malformed_hash_never_verifies(stored: str) -> None:
    assert not verify_password("correct horse battery", stored)


def test_session_token_hash_matches() -> None:
    token, token_hash = new_session_token()
    assert len(token) >= 43
    assert hash_token(token) == token_hash
    assert token not in token_hash
