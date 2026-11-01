"""Fernet key management for credentials stored in the database.

The key file is created on first use (mode 0600). Back it up together with
the database: without it the stored credentials cannot be decrypted and must
be entered again on the Connectors page.
"""

import contextlib
import os
import tempfile
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet


@lru_cache
def cipher_for(key_file: Path) -> Fernet:
    if not key_file.exists():
        _create_key_file(key_file)
    try:
        return Fernet(key_file.read_bytes().strip())
    except ValueError as exc:
        # Not a ValueError: the app-wide handler would answer that as a 422.
        msg = (
            f"Key file {key_file} does not hold a valid Fernet key: restore it from a "
            "backup, or delete it and enter the credentials again on the Connectors page"
        )
        raise RuntimeError(msg) from exc


def _create_key_file(key_file: Path) -> None:
    # Write a complete temp file, then hard-link it into place: a racing
    # thread or process never reads a half-written key, and a crash leaves
    # no empty target. Losing the link race means the winner's key stands.
    key_file.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=key_file.parent, prefix=".atlas-key-")  # mode 0600
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(Fernet.generate_key())
        with contextlib.suppress(FileExistsError):
            os.link(temp, key_file)
    finally:
        os.unlink(temp)
