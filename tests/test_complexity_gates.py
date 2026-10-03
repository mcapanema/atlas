"""Canary for the complexity ceilings CI's lint job enforces.

`ruff check .` gates C901/PLR09xx with the ceilings in pyproject.toml. If a
rule is dropped from `select` or exempted too broadly, `ruff check` would stay
green and the gate would vanish silently, so this test lints a grossly
over-complex function and fails unless every ceiling still fires. It
deliberately doesn't pin the ceiling values: tuning them is legitimate,
removing them isn't.
"""

import json
import subprocess
import sys

_COMPLEXITY_GATES = {"C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915"}


def _absurdly_complex_function() -> str:
    params = ", ".join(f"p{i}" for i in range(20))
    branches = "".join(f"    if p0 == {i}:\n        x = {i}\n        return x\n" for i in range(40))
    return f"def absurd({params}):\n{branches}    return None\n"


def _ruff_codes(source: str, filename: str) -> set[str]:
    result = subprocess.run(  # noqa: S603 — fixed argv; filename is a test constant
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--exit-zero",
            "--output-format",
            "json",
            "--stdin-filename",
            filename,
            "-",
        ],
        input=source,
        capture_output=True,
        text=True,
        check=True,
    )
    return {violation["code"] for violation in json.loads(result.stdout)}


def test_ruff_enforces_every_complexity_ceiling_on_app_code() -> None:
    codes = _ruff_codes(_absurdly_complex_function(), "app/domain/_gate_canary.py")

    assert not _COMPLEXITY_GATES - codes, (
        f"complexity gates not firing: {_COMPLEXITY_GATES - codes}"
    )
