from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "scripts" / "run-act.sh"


def _write_command(directory: Path, name: str, body: str) -> None:
    command = directory / name
    command.write_text(f"#!/bin/sh\nset -eu\n{body}\n", encoding="utf-8")
    command.chmod(0o755)


def test_act_launcher_starts_default_podman_machine_before_checking_socket(tmp_path: Path) -> None:
    commands = tmp_path / "bin"
    commands.mkdir()
    host_socket_path = tmp_path / "missing-podman.sock"
    log = tmp_path / "calls.log"

    _write_command(
        commands,
        "podman",
        """
printf 'podman %s\\n' "$*" >> "$FAKE_LOG"
case "$*" in
  "machine inspect podman-machine-default") exit 0 ;;
  *"--format {{.State}}") printf 'stopped\\n' ;;
  *"--format {{.ConnectionInfo.PodmanSocket.Path}}") printf '%s\\n' "$FAKE_SOCKET" ;;
  "machine start podman-machine-default") exit 0 ;;
  "machine ssh podman-machine-default id -u") printf '501\\n' ;;
  *) exit 2 ;;
esac
""",
    )
    _write_command(
        commands,
        "act",
        'printf \'act DOCKER_HOST=%s args=%s\\n\' "$DOCKER_HOST" "$*" >> "$FAKE_LOG"',
    )

    result = subprocess.run(
        [str(LAUNCHER), "pull_request", "--job", "check", "--pull=false"],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PATH": f"{commands}:/usr/bin:/bin",
            "FAKE_LOG": str(log),
            "FAKE_SOCKET": str(host_socket_path),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    calls = log.read_text(encoding="utf-8")
    assert "machine start podman-machine-default" in calls
    assert "Podman socket is unavailable" in result.stderr
    assert "act DOCKER_HOST=" not in calls


def test_act_launcher_falls_back_to_running_docker(tmp_path: Path) -> None:
    commands = tmp_path / "bin"
    commands.mkdir()
    _write_command(commands, "docker", 'test "$1" = "info"')
    _write_command(commands, "act", "printf 'docker act %s\\n' \"$*\"")

    result = subprocess.run(
        [str(LAUNCHER), "pull_request", "--job", "check", "--pull=false"],
        cwd=REPO_ROOT,
        env={**os.environ, "PATH": f"{commands}:/usr/bin:/bin", "DOCKER_HOST": "fixture"},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "CONTAINER: Docker fallback (fixture)" in result.stdout
    assert "docker act pull_request --job check --pull=false" in result.stdout
