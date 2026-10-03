"""Layer boundaries from CLAUDE.md, enforced as a test instead of a convention.

Scans every import (module-level and function-local, absolute and relative)
under a layer. A failure lists each offending `file:line` and the module it
imports, resolved to its absolute dotted name.
"""

import ast
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"


def _imports(layer_dir: Path) -> list[tuple[str, str]]:
    """(`file:line`, absolute module) for every import under `layer_dir`.

    `layer_dir` must sit inside the top-level package (e.g. `<root>/app/domain`)
    so relative imports resolve against the file's real dotted package.
    """
    root = layer_dir.parent.parent
    found: list[tuple[str, str]] = []
    for path in sorted(layer_dir.rglob("*.py")):
        location = path.relative_to(layer_dir.parent)
        package = ".".join(path.relative_to(root).parent.parts)
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if isinstance(node, ast.Import):
                found.extend((f"{location}:{node.lineno}", a.name) for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                # level 1 is the file's own package, each extra level one up.
                base = package.rsplit(".", node.level - 1)[0] if node.level else ""
                module = ".".join(part for part in (base, node.module) if part)
                found.append((f"{location}:{node.lineno}", module))
                # `from app import api` imports the submodule `app.api` too.
                found.extend(
                    (f"{location}:{node.lineno}", f"{module}.{a.name}")
                    for a in node.names
                    if a.name != "*"
                )
    return found


def _is_under(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == p or module.startswith(f"{p}.") for p in prefixes)


def _is_stdlib(module: str) -> bool:
    return module.split(".")[0] in sys.stdlib_module_names


def test_scanner_reports_function_local_imports(tmp_path: Path) -> None:
    layer = tmp_path / "app" / "domain"
    layer.mkdir(parents=True)
    (layer / "leaky.py").write_text(
        "import json\n\n\ndef f() -> None:\n    from sqlalchemy import select\n"
    )
    assert sorted(_imports(layer)) == [
        ("domain/leaky.py:1", "json"),
        ("domain/leaky.py:5", "sqlalchemy"),
        ("domain/leaky.py:5", "sqlalchemy.select"),
    ]


def test_scanner_resolves_relative_imports(tmp_path: Path) -> None:
    layer = tmp_path / "app" / "domain"
    (layer / "metrics").mkdir(parents=True)
    (layer / "metrics" / "leaky.py").write_text(
        "from . import stats\nfrom ..teams import entities\nfrom ...infrastructure import db\n"
    )
    assert sorted(_imports(layer)) == [
        ("domain/metrics/leaky.py:1", "app.domain.metrics"),
        ("domain/metrics/leaky.py:1", "app.domain.metrics.stats"),
        ("domain/metrics/leaky.py:2", "app.domain.teams"),
        ("domain/metrics/leaky.py:2", "app.domain.teams.entities"),
        ("domain/metrics/leaky.py:3", "app.infrastructure"),
        ("domain/metrics/leaky.py:3", "app.infrastructure.db"),
    ]


def test_scanner_reports_layer_imported_via_package_name(tmp_path: Path) -> None:
    layer = tmp_path / "app" / "infrastructure"
    layer.mkdir(parents=True)
    (layer / "leaky.py").write_text("from app import api\nfrom .. import api as sibling\n")
    leaks = [
        loc for loc, module in _imports(layer) if _is_under(module, ("app.application", "app.api"))
    ]
    assert leaks == ["infrastructure/leaky.py:1", "infrastructure/leaky.py:2"]


def test_domain_imports_only_stdlib_and_itself() -> None:
    offenders = [
        f"{loc} imports {module}"
        for loc, module in _imports(APP / "domain")
        if not (_is_stdlib(module) or _is_under(module, ("app.domain",)))
    ]
    assert offenders == []


def test_application_imports_only_stdlib_domain_and_itself() -> None:
    offenders = [
        f"{loc} imports {module}"
        for loc, module in _imports(APP / "application")
        if not (_is_stdlib(module) or _is_under(module, ("app.domain", "app.application")))
    ]
    assert offenders == []


def test_infrastructure_never_imports_application_or_api() -> None:
    offenders = [
        f"{loc} imports {module}"
        for loc, module in _imports(APP / "infrastructure")
        if _is_under(module, ("app.application", "app.api"))
    ]
    assert offenders == []
