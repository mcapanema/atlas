import json
import re
from pathlib import Path


def test_uvicorn_replaces_the_shell_so_docker_stop_reaches_it() -> None:
    # `sh -c "a && b"` keeps sh as PID 1, and sh doesn't pass SIGTERM on: uvicorn
    # would die without its lifespan shutdown and leave data/atlas.db.lease behind,
    # refusing the next start for LEASE_TTL_SECONDS.
    cmd = re.search(r"^CMD (.+)$", Path("Dockerfile").read_text(), re.MULTILINE)
    assert cmd is not None
    assert "&& exec uvicorn " in json.loads(cmd.group(1))[-1]
