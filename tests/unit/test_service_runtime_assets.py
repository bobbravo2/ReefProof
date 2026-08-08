from __future__ import annotations

import os
import time
from pathlib import Path

from reefproof.service.runtime import _workbench_assets_require_rebuild


def _write(path: Path, contents: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def _set_mtime(path: Path, timestamp: float) -> None:
    os.utime(path, (timestamp, timestamp))


def test_workbench_asset_rebuild_gate_distinguishes_stale_and_fresh(tmp_path: Path) -> None:
    repo = tmp_path
    workbench_ts = repo / "src/reefproof/api/web/typescript/workbench.ts"
    workbench_js = repo / "src/reefproof/api/web/static/workbench.js"
    tsconfig = repo / "tsconfig.json"
    package_json = repo / "package.json"

    _write(workbench_ts)
    _write(tsconfig, "{}")
    _write(package_json, "{}")

    # Missing generated output always requires a rebuild.
    assert _workbench_assets_require_rebuild(repo) is True

    _write(workbench_js)
    now = time.time()
    _set_mtime(workbench_ts, now)
    _set_mtime(tsconfig, now)
    _set_mtime(package_json, now)
    _set_mtime(workbench_js, now + 5)

    # Generated output newer than all inputs does not require a rebuild.
    assert _workbench_assets_require_rebuild(repo) is False

    _set_mtime(workbench_ts, now + 10)

    # Any newer input marks the output as stale.
    assert _workbench_assets_require_rebuild(repo) is True
