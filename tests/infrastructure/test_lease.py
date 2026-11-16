import json
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.infrastructure.database import lease as lease_module
from app.infrastructure.database.lease import (
    DatabaseInUseError,
    LeaseFileError,
    acquire_sqlite_lease,
)


def _url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'atlas.db'}"


def _lease_path(tmp_path: Path) -> Path:
    return tmp_path / "atlas.db.lease"


def _write_lease(
    path: Path,
    *,
    host: str,
    pid: int,
    heartbeat: float,
    token: str = "other",  # noqa: S107 — a lease token, not a password
) -> None:
    path.write_text(json.dumps({"token": token, "host": host, "pid": pid, "heartbeat": heartbeat}))


def test_acquire_writes_a_lease_and_release_removes_it(tmp_path: Path) -> None:
    lease = acquire_sqlite_lease(_url(tmp_path))
    data = json.loads(_lease_path(tmp_path).read_text())
    assert data["host"] == socket.gethostname()
    assert data["pid"] == os.getpid()
    lease.release()
    assert not _lease_path(tmp_path).exists()


def test_release_twice_is_harmless(tmp_path: Path) -> None:
    lease = acquire_sqlite_lease(_url(tmp_path))
    lease.release()
    lease.release()
    assert not _lease_path(tmp_path).exists()


def test_refuses_a_live_lease_of_another_host(tmp_path: Path) -> None:
    _write_lease(_lease_path(tmp_path), host="docker-abc", pid=1, heartbeat=1000.0)
    with pytest.raises(DatabaseInUseError, match=r"docker-abc.*make docker-down"):
        acquire_sqlite_lease(_url(tmp_path), now=lambda: 1000.0 + 60)
    assert json.loads(_lease_path(tmp_path).read_text())["token"] == "other"


def test_takes_over_a_stale_lease_of_another_host(tmp_path: Path) -> None:
    _write_lease(_lease_path(tmp_path), host="docker-abc", pid=1, heartbeat=1000.0)
    lease = acquire_sqlite_lease(_url(tmp_path), now=lambda: 1000.0 + 91)
    assert json.loads(_lease_path(tmp_path).read_text())["host"] == socket.gethostname()
    lease.release()


def test_takes_over_a_lease_from_its_own_host_and_pid(tmp_path: Path) -> None:
    # A restarted container: same hostname, and often the same pid.
    _write_lease(
        _lease_path(tmp_path), host=socket.gethostname(), pid=os.getpid(), heartbeat=time.time()
    )
    acquire_sqlite_lease(_url(tmp_path)).release()


def test_takes_over_a_lease_whose_pid_is_dead_on_this_host(tmp_path: Path) -> None:
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    _write_lease(
        _lease_path(tmp_path), host=socket.gethostname(), pid=dead.pid, heartbeat=time.time()
    )
    acquire_sqlite_lease(_url(tmp_path)).release()


def test_shares_a_live_lease_of_its_own_host(tmp_path: Path) -> None:
    # `docker compose exec app python -m app.cli ...` beside the running server:
    # one kernel, so SQLite's own locks work; the owner keeps its lease.
    alive = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        _write_lease(
            _lease_path(tmp_path), host=socket.gethostname(), pid=alive.pid, heartbeat=time.time()
        )
        lease = acquire_sqlite_lease(_url(tmp_path))
        assert lease.path is None
        lease.release()
        assert json.loads(_lease_path(tmp_path).read_text())["token"] == "other"
    finally:
        alive.kill()
        alive.wait()


def test_renews_by_wall_clock_after_a_sleep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A laptop sleep stops the monotonic clock that Event.wait uses: renewal must
    # follow the wall clock, or a live lease looks stale right after wake-up.
    monkeypatch.setattr(lease_module, "_TICK_SECONDS", 0.01)
    times = iter([1000.0, 1000.0])
    lease = acquire_sqlite_lease(_url(tmp_path), now=lambda: next(times, 5000.0))
    try:
        deadline = time.monotonic() + 1
        while json.loads(_lease_path(tmp_path).read_text())["heartbeat"] != 5000.0:
            assert time.monotonic() < deadline, "no renewal after the wall clock jumped"
            time.sleep(0.01)
    finally:
        lease.release()


def test_unreadable_lease_is_taken_over(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    _lease_path(tmp_path).write_text("{not json")
    with caplog.at_level(logging.WARNING):
        acquire_sqlite_lease(_url(tmp_path)).release()
    assert "atlas.db.lease" in caplog.text


def test_release_keeps_a_lease_another_process_took_over(tmp_path: Path) -> None:
    lease = acquire_sqlite_lease(_url(tmp_path))
    _write_lease(_lease_path(tmp_path), host="docker-abc", pid=1, heartbeat=time.time())
    lease.release()
    assert json.loads(_lease_path(tmp_path).read_text())["host"] == "docker-abc"


def test_heartbeat_renews_while_held(tmp_path: Path) -> None:
    clock = iter(range(1000, 2000))
    lease = acquire_sqlite_lease(_url(tmp_path), now=lambda: float(next(clock)), renew_every=0.01)
    try:
        first = json.loads(_lease_path(tmp_path).read_text())["heartbeat"]
        deadline = time.monotonic() + 1
        while json.loads(_lease_path(tmp_path).read_text())["heartbeat"] == first:
            assert time.monotonic() < deadline, "the heartbeat never renewed"
            time.sleep(0.01)
    finally:
        lease.release()


def test_heartbeat_stops_after_another_process_takes_over(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    lease = acquire_sqlite_lease(_url(tmp_path), renew_every=0.01)
    _write_lease(_lease_path(tmp_path), host="docker-abc", pid=1, heartbeat=1.0)
    with caplog.at_level(logging.ERROR):
        time.sleep(0.1)
    lease.release()
    assert json.loads(_lease_path(tmp_path).read_text())["heartbeat"] == 1.0
    assert "took over" in caplog.text


@pytest.mark.parametrize(
    "url",
    [
        "sqlite+aiosqlite://",
        "sqlite+aiosqlite:///:memory:",
        "postgresql+asyncpg://u:p@127.0.0.1:1/atlas",
    ],
)
def test_non_file_urls_get_a_no_op_lease(url: str) -> None:
    lease = acquire_sqlite_lease(url)
    assert lease.path is None
    lease.release()


def test_missing_directory_gives_a_no_op_lease(tmp_path: Path) -> None:
    lease = acquire_sqlite_lease(f"sqlite+aiosqlite:///{tmp_path / 'no-such-dir' / 'atlas.db'}")
    assert lease.path is None
    assert not (tmp_path / "no-such-dir").exists()


def test_in_use_message_names_the_remaining_wait(tmp_path: Path) -> None:
    _write_lease(_lease_path(tmp_path), host="docker-abc", pid=1, heartbeat=1000.0)
    with pytest.raises(DatabaseInUseError) as caught:
        acquire_sqlite_lease(_url(tmp_path), now=lambda: 1000.0 + 60)
    message = str(caught.value)
    assert "If it is running, stop it first (Docker: make docker-down)." in message
    assert "If it already stopped, wait 30 s" in message
    assert str(_lease_path(tmp_path)) in message


def test_in_use_message_never_asks_for_a_zero_wait(tmp_path: Path) -> None:
    _write_lease(_lease_path(tmp_path), host="docker-abc", pid=1, heartbeat=1000.0)
    with pytest.raises(DatabaseInUseError, match=r"wait 1 s"):
        acquire_sqlite_lease(_url(tmp_path), now=lambda: 1000.0 + 89.6)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_unwritable_directory_is_a_lease_file_error(tmp_path: Path) -> None:
    tmp_path.chmod(0o500)
    try:
        with pytest.raises(
            LeaseFileError, match=r"Can't write the SQLite lease file .*atlas\.db\.lease"
        ):
            acquire_sqlite_lease(_url(tmp_path))
    finally:
        tmp_path.chmod(0o700)
