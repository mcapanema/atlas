from pathlib import Path

from app.infrastructure.secrets import cipher_for


def test_creates_a_private_key_file_when_missing(tmp_path: Path) -> None:
    key_file = tmp_path / "nested" / "atlas.key"
    cipher = cipher_for(key_file)
    assert key_file.stat().st_mode & 0o777 == 0o600
    assert cipher.decrypt(cipher.encrypt(b"x")) == b"x"


def test_reuses_an_existing_key_file(tmp_path: Path) -> None:
    key_file = tmp_path / "atlas.key"
    token = cipher_for(key_file).encrypt(b"secret")
    cipher_for.cache_clear()
    assert cipher_for(key_file).decrypt(token) == b"secret"
