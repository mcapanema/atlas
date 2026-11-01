import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

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


def test_concurrent_first_use_agrees_on_one_key(tmp_path: Path) -> None:
    # Cache misses aren't serialized: threads racing on a fresh install must
    # never read a half-written key file.
    create = cipher_for.__wrapped__
    for attempt in range(20):
        key_file = tmp_path / f"atlas-{attempt}.key"
        barrier = threading.Barrier(8)

        def first_use(key_file: Path = key_file, barrier: threading.Barrier = barrier) -> Fernet:
            barrier.wait()
            return create(key_file)

        with ThreadPoolExecutor(max_workers=8) as pool:
            ciphers = list(pool.map(lambda _: first_use(), range(8)))
        token = ciphers[0].encrypt(b"x")
        assert all(cipher.decrypt(token) == b"x" for cipher in ciphers)
        assert key_file.stat().st_mode & 0o777 == 0o600
        assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
            f"atlas-{n}.key" for n in range(attempt + 1)
        )  # no temp file left behind


def test_a_corrupt_key_file_names_its_path(tmp_path: Path) -> None:
    key_file = tmp_path / "atlas.key"
    key_file.write_bytes(b"")
    with pytest.raises(RuntimeError, match=re.escape(str(key_file))) as raised:
        cipher_for(key_file)
    assert not isinstance(raised.value, ValueError)  # the global handler turns those into 422
