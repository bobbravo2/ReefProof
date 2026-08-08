from __future__ import annotations

import ast
from pathlib import Path

SOURCE_ROOT = Path("src/reefproof")
FORBIDDEN_CLIENT_ROOTS = frozenset({"awsiot", "paho", "pyhydros"})


def _import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.partition(".")[0])
    return roots


def test_runtime_has_no_mqtt_capability_before_transport_adr() -> None:
    python_files = sorted(SOURCE_ROOT.rglob("*.py"))
    mqtt_named = [path for path in python_files if "mqtt" in path.name.casefold()]
    forbidden_imports = {
        str(path): sorted(_import_roots(path) & FORBIDDEN_CLIENT_ROOTS)
        for path in python_files
        if _import_roots(path) & FORBIDDEN_CLIENT_ROOTS
    }

    assert mqtt_named == []
    assert forbidden_imports == {}
