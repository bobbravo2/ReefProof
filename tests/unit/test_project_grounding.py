from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(".codex/skills/reefproof-project-grounding/scripts/extract.py")


def load_module():
    spec = importlib.util.spec_from_file_location("reefproof_project_grounding_extract", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_extractor(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def write_repo(
    tmp_path: Path,
    *,
    version: str = "0.1.0",
    module_version: str | None = None,
    initialize_git: bool = False,
) -> Path:
    repo = tmp_path / "repo"
    (repo / ".agent").mkdir(parents=True)
    (repo / ".codex/skills/reefproof-project-grounding/scripts").mkdir(parents=True)
    (repo / "src/reefproof").mkdir(parents=True)
    (repo / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n', encoding="utf-8")
    (repo / "src/reefproof/__init__.py").write_text(
        f'"""ReefProof product shell."""\n\n__version__ = "{module_version or version}"\n',
        encoding="utf-8",
    )
    (repo / "AGENTS.md").write_text(
        "# ReefProof Agent Guide\n\nReefProof may observe, model, challenge, "
        "and alert on a living system. "
        "It may not silently take control of one.\n",
        encoding="utf-8",
    )
    (repo / ".agent/next-task.md").write_text(
        "Import one real offline HYDROS snapshot through a shared application operation.\n",
        encoding="utf-8",
    )
    (repo / ".agent/project-context.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "product": {"name": "ReefProof"},
                "current_gate": "ReefProof passes when one real offline HYDROS snapshot produces a "
                "persisted, materially useful configuration finding that Customer 0 verifies.",
                "architecture": {
                    "main_cli_entrypoint": "src/reefproof/cli.py",
                    "runtime_composition_entrypoint": "src/reefproof/service/runtime.py",
                    "persistence_entrypoint": "src/reefproof/storage/database.py",
                },
                "implemented": ["offline authored configuration normalization"],
                "deferred": ["TOTP-backed trust controls"],
                "absent": ["validated real HYDROS snapshot importer"],
                "unknowns": ["exact first real HYDROS snapshot structure"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    for path in (
        "src/reefproof/cli.py",
        "src/reefproof/service/runtime.py",
        "src/reefproof/storage/database.py",
    ):
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# stub\n", encoding="utf-8")
    if initialize_git:
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "ReefProof Test")
        git(repo, "config", "user.email", "reefproof-test@example.invalid")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "test")
    return repo


def build_output(repo: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    module = load_module()
    values = {
        ("branch", "--show-current"): "main",
        ("rev-parse", "HEAD"): "0123456789abcdef",
        ("status", "--short"): "",
    }
    monkeypatch.setattr(module, "git", lambda _repo, *args: values[args])
    return module.build_output(repo)


def test_grounding_cli_lifecycle_is_exact_deterministic_read_only_and_git_aware(
    tmp_path: Path,
) -> None:
    repo = write_repo(tmp_path, initialize_git=True)
    before = sorted(path.relative_to(repo).as_posix() for path in repo.rglob("*") if path.is_file())

    first = run_extractor(repo, "--format", "json")
    second = run_extractor(repo, "--format", "json")
    text = run_extractor(repo)

    after = sorted(path.relative_to(repo).as_posix() for path in repo.rglob("*") if path.is_file())
    assert first.returncode == second.returncode == text.returncode == 0
    assert first.stderr == second.stderr == text.stderr == ""
    assert first.stdout == second.stdout
    assert before == after

    clean = json.loads(first.stdout)
    assert clean["product"]["display_identity"] == "ReefProof 0.1.0"
    assert clean["git_state"]["working_tree"] == "clean"
    assert "SOURCES" in text.stdout
    for path in (
        ".agent/project-context.json",
        ".agent/next-task.md",
        "AGENTS.md",
        "pyproject.toml",
        "src/reefproof/__init__.py",
    ):
        assert path in text.stdout

    (repo / "new.txt").write_text("dirty\n", encoding="utf-8")
    dirty = json.loads(run_extractor(repo, "--format", "json").stdout)
    assert dirty["git_state"]["working_tree"] == "dirty"


def test_grounding_llm_format_is_compact_deterministic_and_steering_aware(
    tmp_path: Path,
) -> None:
    repo = write_repo(tmp_path, initialize_git=True)
    (repo / "AGENTS.md").write_text(
        "# ReefProof Agent Guide\n\n"
        "ReefProof may observe, model, challenge, and alert on a living system. "
        "It may not silently take control of one.\n\n"
        "- **Read-only review:** inspect and report.\n"
        "- **Small compatible repair:** preserve interfaces.\n"
        "- **Material change:** create a dated plan.\n\n"
        "CLI or REPL: exercise the affected path through attached-TTY `./reefproof`.\n"
        "API or browser: start the service and inspect the affected endpoint or browser flow.\n"
        "Shell launcher: run `bash -n` on the shell file.\n"
        "Internal Python behavior: run focused automated tests.\n",
        encoding="utf-8",
    )
    (repo / ".agent/next-task.md").write_text(
        """# Next Task

## Outcome

Make grounding efficient for small models.

## Completion criteria

- Preserve JSON.
- Emit compact steering.

## Boundary

No network or LLM calls.
""",
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "structured task")
    manifest = json.loads((repo / ".agent/project-context.json").read_text(encoding="utf-8"))

    compact = run_extractor(repo, "--format", "llm")
    first = run_extractor(repo, "--format", "llm", "--detail")
    second = run_extractor(repo, "--format", "llm", "--detail")

    assert compact.returncode == first.returncode == second.returncode == 0
    assert compact.stderr == first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    assert '"source"' not in first.stdout
    assert {line.split(" ", 1)[0] for line in compact.stdout.splitlines()} == {
        "P",
        "S",
        "R",
        "V",
        "W",
        "G",
        "N",
        "C",
        "B",
        "T",
    }
    assert len(compact.stdout) < len(first.stdout)
    assert first.stdout.splitlines() == [
        "P ReefProof 0.1.0",
        "S ReefProof may observe, model, challenge, and alert on a living system. "
        "It may not silently take control of one.",
        "R review=inspect/report;repair=focused+exact-interface;material=plan+repo-gate+human",
        "V cli/repl=attached-TTY;api/browser=affected-flow;shell=bash-n;python=focused-tests",
        "W preserve-WIP;inspect-task-diff;stop-on-unclear-overlap",
        f"G {manifest['current_gate']}",
        "A main_cli_entrypoint=src/reefproof/cli.py;"
        "runtime_composition_entrypoint=src/reefproof/service/runtime.py;"
        "persistence_entrypoint=src/reefproof/storage/database.py",
        "I offline authored configuration normalization",
        "D TOTP-backed trust controls",
        "X validated real HYDROS snapshot importer",
        "U exact first real HYDROS snapshot structure",
        "N Make grounding efficient for small models.",
        "C Preserve JSON. | Emit compact steering.",
        "B No network or LLM calls.",
        "T main@" + git(repo, "rev-parse", "HEAD").stdout.strip() + " clean",
    ]


def test_grounding_llm_format_rejects_missing_agent_steering(tmp_path: Path) -> None:
    repo = write_repo(tmp_path, initialize_git=True)

    result = run_extractor(repo, "--format", "llm")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "grounding steering marker" in result.stderr


def test_agent_guidance_uses_progressive_grounding_disclosure() -> None:
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    startup = agents.split("## Start and task routing", 1)[1].split("##", 1)[0]
    skill = Path(".codex/skills/reefproof-project-grounding/SKILL.md").read_text(encoding="utf-8")

    assert startup.index("extract.py --repo . --format llm`") < startup.index("`--detail`")
    assert startup.index("`--detail`") < startup.index("`--format json`")
    compact_command = "extract.py --repo . --format llm\n"
    detail_command = "extract.py --repo . --format llm --detail"
    json_command = "extract.py --repo . --format json"
    assert skill.index(compact_command) < skill.index(detail_command) < skill.index(json_command)


def test_grounding_uses_current_version_without_hardcoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_repo(tmp_path, version="0.2.3")
    payload = build_output(repo, monkeypatch)
    assert payload["product"]["display_identity"] == "ReefProof 0.2.3"


def test_grounding_rejects_invalid_semver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = write_repo(tmp_path, version="0.1")
    with pytest.raises(ValueError, match=r"major\.minor\.patch"):
        build_output(repo, monkeypatch)


def test_grounding_rejects_version_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_repo(tmp_path, version="0.1.0", module_version="0.1.1")
    with pytest.raises(ValueError, match="must match"):
        build_output(repo, monkeypatch)


def test_grounding_requires_exact_safety_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_repo(tmp_path)
    (repo / "AGENTS.md").write_text("# ReefProof Agent Guide\n\nbroken\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exact permanent safety boundary"):
        build_output(repo, monkeypatch)


def test_grounding_keeps_implemented_and_deferred_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_repo(tmp_path)
    payload = build_output(repo, monkeypatch)
    manifest = json.loads((repo / ".agent/project-context.json").read_text(encoding="utf-8"))
    assert payload["implemented"]["value"] == manifest["implemented"]
    assert payload["deferred"]["value"] == manifest["deferred"]


def test_grounding_reads_only_bounded_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_repo(tmp_path, initialize_git=True)
    module = load_module()
    reads: list[str] = []
    git_calls: list[tuple[str, ...]] = []
    real_read_text = module.read_text
    real_git = module.git

    def traced_read_text(test_repo: Path, relative_path: str) -> str:
        reads.append(relative_path)
        return real_read_text(test_repo, relative_path)

    def traced_git(test_repo: Path, *args: str) -> str:
        git_calls.append(args)
        return real_git(test_repo, *args)

    monkeypatch.setattr(module, "read_text", traced_read_text)
    monkeypatch.setattr(module, "git", traced_git)
    output = module.build_output(repo)
    assert output["product"]["display_identity"] == "ReefProof 0.1.0"
    assert reads == [
        ".agent/project-context.json",
        ".agent/next-task.md",
        "AGENTS.md",
        "pyproject.toml",
        "src/reefproof/__init__.py",
    ]
    assert git_calls == [
        ("branch", "--show-current"),
        ("rev-parse", "HEAD"),
        ("status", "--short"),
    ]


def test_grounding_rejects_malformed_project_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_repo(tmp_path)
    (repo / ".agent/project-context.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        build_output(repo, monkeypatch)


def test_grounding_rejects_missing_architecture_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_repo(tmp_path)
    manifest = json.loads((repo / ".agent/project-context.json").read_text(encoding="utf-8"))
    manifest["architecture"]["persistence_entrypoint"] = "src/reefproof/missing.py"
    (repo / ".agent/project-context.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="existing file"):
        build_output(repo, monkeypatch)


def test_grounding_rejects_disallowed_derived_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_repo(tmp_path)
    manifest = json.loads((repo / ".agent/project-context.json").read_text(encoding="utf-8"))
    manifest["product"]["version"] = "0.1.0"
    manifest["safety_boundary"] = "bad"
    (repo / ".agent/project-context.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=r"must not define|derived top-level fields"):
        build_output(repo, monkeypatch)


def test_grounding_requires_non_whitespace_next_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_repo(tmp_path)
    (repo / ".agent/next-task.md").write_text("   \n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty text"):
        build_output(repo, monkeypatch)


def test_grounding_rejects_non_relative_architecture_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_repo(tmp_path)
    manifest = json.loads((repo / ".agent/project-context.json").read_text(encoding="utf-8"))
    manifest["architecture"]["main_cli_entrypoint"] = "/tmp/reefproof.py"
    (repo / ".agent/project-context.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="must be relative"):
        build_output(repo, monkeypatch)


def test_grounding_rejects_architecture_escape_outside_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_repo(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("# out\n", encoding="utf-8")
    (repo / "src/reefproof/link.py").symlink_to(outside)
    manifest = json.loads((repo / ".agent/project-context.json").read_text(encoding="utf-8"))
    manifest["architecture"]["main_cli_entrypoint"] = "src/reefproof/link.py"
    (repo / ".agent/project-context.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="stay inside the repository"):
        build_output(repo, monkeypatch)


def test_grounding_rejects_architecture_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_repo(tmp_path)
    manifest = json.loads((repo / ".agent/project-context.json").read_text(encoding="utf-8"))
    manifest["architecture"]["main_cli_entrypoint"] = "src/reefproof"
    (repo / ".agent/project-context.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="existing file"):
        build_output(repo, monkeypatch)
