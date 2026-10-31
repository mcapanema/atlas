"""Fernet key management for credentials stored in the database.

The key file is created on first use (mode 0600). Back it up together with
the database: without it the stored credentials cannot be decrypted and must
be entered again on the Connectors page.
"""

import os
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet


@lru_cache
def cipher_for(key_file: Path) -> Fernet:
    key_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return Fernet(key_file.read_bytes().strip())
    key = Fernet.generate_key()
    with os.fdopen(fd, "wb") as handle:
        handle.write(key)
    return Fernet(key)
