"""A lease file that keeps a second Atlas process off a SQLite file.

data/atlas.db is shared by local runs and the Compose container, and SQLite's
file locks don't cross Docker Desktop's VM. A second process that opens the
file anyway also switches its journal mode at startup, which turned the
container's rollback journal into WAL over the bind mount and ended in
"disk I/O error" (2026-11-16). File contents do cross the bind mount, so each
process writes ``<db>.lease`` (owner + heartbeat) and a renew thread keeps it
fresh; another process refuses to start while that lease is live.
"""

import json
import logging
import os
import socket
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.engine import make_url

logger = logging.getLogger(__name__)

# The auto-sync tick runs every 60 s; a lease older than this has missed
# several renewals, so its owner is gone.
LEASE_TTL_SECONDS = 90.0
RENEW_SECONDS = 30.0
_TICK_SECONDS = 1.0  # how often the renew thread checks the wall clock


class DatabaseInUseError(RuntimeError):
    """Another live Atlas process holds the SQLite file's lease."""


class _Owner:
    def __init__(self, token: str, host: str, pid: int, heartbeat: float) -> None:
        self.token, self.host, self.pid, self.heartbeat = token, host, pid, heartbeat


def _read_owner(path: Path) -> _Owner | None:
    """The lease's owner; None when there is no lease or it can't be read."""
    try:
        data = json.loads(path.read_text())
        return _Owner(
            str(data["token"]), str(data["host"]), int(data["pid"]), float(data["heartbeat"])
        )
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError, KeyError):
        logger.warning("Ignoring the unreadable SQLite lease file %s; taking it over", path)
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # alive, but another user's
        return True
    return True


def _shares_with(owner: _Owner) -> bool:
    """True when ``owner`` is a live process on this host.

    One kernel means SQLite's own locks work, so a second process here (the
    CLI beside the server, via `docker compose exec`) may use the file; it
    leaves the owner's lease alone. A dead pid, or our own (a container
    restart reuses pid 1), is a crashed owner to take over.
    """
    return owner.host == socket.gethostname() and owner.pid != os.getpid() and _pid_alive(owner.pid)


class SqliteLease:
    """A held lease on one SQLite file; ``path`` is None for a no-op lease."""

    def __init__(
        self,
        path: Path | None,
        *,
        now: Callable[[], float] = time.time,
        renew_every: float = RENEW_SECONDS,
    ) -> None:
        self.path = path
        self._token = uuid.uuid4().hex
        self._now = now
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        if path is not None:
            self._write()
            self._thread = threading.Thread(
                target=self._renew_loop, args=(renew_every,), name="sqlite-lease", daemon=True
            )
            self._thread.start()

    def _write(self) -> None:
        assert self.path is not None  # noqa: S101 — narrow for mypy; only held leases write
        self._heartbeat = self._now()
        record = {
            "token": self._token,
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "heartbeat": self._heartbeat,
        }
        tmp = self.path.with_name(f"{self.path.name}.tmp")
        tmp.write_text(json.dumps(record))
        os.replace(tmp, self.path)

    def _renew_loop(self, renew_every: float) -> None:
        assert self.path is not None  # noqa: S101 — narrow for mypy; only held leases renew
        # Wake often and renew by the wall clock: Event.wait's monotonic clock
        # stops while a laptop sleeps, and a lease must not look stale after wake-up.
        while not self._stop.wait(min(_TICK_SECONDS, renew_every)):
            if self._now() - self._heartbeat < renew_every:
                continue
            owner = _read_owner(self.path)
            if owner is not None and owner.token != self._token:
                logger.error("Another process took over the SQLite lease %s", self.path)
                return
            try:
                self._write()
            except OSError:
                logger.warning("Can't renew the SQLite lease %s", self.path, exc_info=True)

    def release(self) -> None:
        """Stop renewing and remove the lease if it is still ours; safe to call twice."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        if self.path is None:
            return
        owner = _read_owner(self.path)
        if owner is not None and owner.token == self._token:
            self.path.unlink(missing_ok=True)


def acquire_sqlite_lease(
    database_url: str,
    *,
    now: Callable[[], float] = time.time,
    renew_every: float = RENEW_SECONDS,
) -> SqliteLease:
    """Take the lease on a SQLite file, or raise DatabaseInUseError; a no-op lease elsewhere.

    A URL that names no file (Postgres, in-memory) or a file in a missing
    directory gets a no-op lease: the latter lets SQLite report its own
    "unable to open" error.
    """
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
        return SqliteLease(None)
    database = url.database
    assert database is not None  # noqa: S101 — narrowed by the guard above
    if not Path(database).parent.is_dir():
        return SqliteLease(None)
    lease_path = Path(f"{database}.lease")
    # ponytail: check-then-replace, not an atomic claim; two processes started
    # in the same instant can both win. Ceiling: one person starting Atlas twice
    # at once. Upgrade path: O_EXCL create plus a stale-lease rename.
    owner = _read_owner(lease_path)
    current = now()
    if owner is not None and _shares_with(owner):
        return SqliteLease(None)
    other_host = owner is not None and owner.host != socket.gethostname()
    if owner is not None and other_host and current - owner.heartbeat < LEASE_TTL_SECONDS:
        raise DatabaseInUseError(
            f"{database} is in use by another Atlas process ({owner.host}, pid {owner.pid},"
            f" seen {current - owner.heartbeat:.0f} s ago). Stop it first (Docker: make"
            f" docker-down). If it crashed, wait {LEASE_TTL_SECONDS:.0f} s or delete {lease_path}."
        )
    return SqliteLease(lease_path, now=now, renew_every=renew_every)
