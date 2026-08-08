from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPOSITORY_ROOT / ".githooks" / "pre-commit"


def _run(
    *arguments: str,
    cwd: Path,
    check: bool = True,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "UV_CACHE_DIR": str(cwd / ".uv-cache"),
            **(extra_env or {}),
        },
    )


def _write(path: Path, content: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def test_pre_commit_checks_staged_snapshot_without_mutating_worktree(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _run("git", "init", "-q", cwd=repository)
    _run("git", "config", "user.email", "test@example.invalid", cwd=repository)
    _run("git", "config", "user.name", "ReefProof Test", cwd=repository)

    shutil.copy2(HOOK, repository / "pre-commit")
    _write(
        repository / "scripts/check-generated-workbench.sh",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "grep -qx staged src/reefproof/api/web/typescript/workbench.ts\n"
        "printf generated > generated-in-snapshot.txt\n",
        executable=True,
    )
    _write(
        repository / "scripts/check-generated-workbench-contracts.sh",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "grep -qx staged src/reefproof/api/web/typescript/workbench.ts\n",
        executable=True,
    )
    _write(
        repository / "tests/integration/test_api.py",
        "def test_openapi_describes_auth_and_groups_only_api_operations() -> None:\n"
        "    assert True\n",
    )
    bin_directory = repository / "bin"
    _write(
        bin_directory / "uv",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'test "$*" = "run pytest -q '
        'tests/integration/test_api.py::test_openapi_describes_auth_and_groups_only_api_operations"\n'
        "grep -q test_openapi_describes_auth_and_groups_only_api_operations "
        "tests/integration/test_api.py\n",
        executable=True,
    )
    workbench = repository / "src/reefproof/api/web/typescript/workbench.ts"
    _write(workbench, "baseline\n")
    _run("git", "add", ".", cwd=repository)
    _run("git", "commit", "-qm", "baseline", cwd=repository)

    workbench.write_text("staged\n", encoding="utf-8")
    _run("git", "add", str(workbench.relative_to(repository)), cwd=repository)
    workbench.write_text("unstaged\n", encoding="utf-8")

    result = _run(
        "bash",
        "pre-commit",
        cwd=repository,
        extra_env={"PATH": f"{bin_directory}{os.pathsep}{os.environ['PATH']}"},
    )

    assert result.returncode == 0
    assert workbench.read_text(encoding="utf-8") == "unstaged\n"
    assert not (repository / "generated-in-snapshot.txt").exists()


def test_pre_commit_rejects_staged_whitespace_errors(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _run("git", "init", "-q", cwd=repository)
    shutil.copy2(HOOK, repository / "pre-commit")
    _write(repository / "notes.txt", "trailing whitespace   \n")
    _run("git", "add", ".", cwd=repository)

    result = _run("bash", "pre-commit", cwd=repository, check=False)

    assert result.returncode != 0
    assert "trailing whitespace" in result.stdout
