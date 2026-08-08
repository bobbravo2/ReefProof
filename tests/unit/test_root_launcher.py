from __future__ import annotations

import os
import pty
import select
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

LAUNCHER = Path("reefproof")


@dataclass
class PtySession:
    """Drive one real terminal process by observed states, never sleeps."""

    master: int
    process: subprocess.Popen[bytes]
    pending: str = ""
    transcript: list[str] = field(default_factory=list)

    def expect(self, expected: str, timeout: float = 15.0) -> str:
        deadline = time.monotonic() + timeout
        while expected not in self.pending and time.monotonic() < deadline:
            readable, _, _ = select.select(
                [self.master], [], [], max(0.0, deadline - time.monotonic())
            )
            if not readable:
                break
            try:
                chunk = os.read(self.master, 4096).decode(errors="replace")
            except OSError:
                break
            self.pending += chunk
            self.transcript.append(chunk)
        if expected not in self.pending:
            raise AssertionError(
                f"did not observe {expected!r}; pending output was {self.pending!r}; "
                f"return code was {self.process.poll()!r}"
            )
        consumed, self.pending = self.pending.split(expected, 1)
        return consumed + expected

    def send(self, characters: bytes) -> None:
        assert self.process.poll() is None, f"process exited with {self.process.returncode}"
        os.write(self.master, characters)

    def read_to_exit(self, timeout: float = 15.0) -> str:
        deadline = time.monotonic() + timeout
        while self.process.poll() is None and time.monotonic() < deadline:
            readable, _, _ = select.select([self.master], [], [], 0.1)
            if not readable:
                continue
            try:
                chunk = os.read(self.master, 4096).decode(errors="replace")
            except OSError:
                break
            self.pending += chunk
            self.transcript.append(chunk)
        self.process.wait(timeout=max(0.1, deadline - time.monotonic()))
        return "".join(self.transcript)

    def close(self) -> None:
        os.close(self.master)
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=2)


def _spawn_pty(arguments: list[str], environment: dict[str, str]) -> PtySession:
    master, slave = pty.openpty()
    process = subprocess.Popen(
        arguments,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=environment,
        close_fds=True,
    )
    os.close(slave)
    return PtySession(master, process)


def _fake_uv_environment(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    uv_log = tmp_path / "uv.log"
    history = tmp_path / "history.log"
    fake_uv = bin_directory / "uv"
    fake_uv.write_text(
        """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_UV_LOG"
if [[ " $* " == *" reefproof menu "* ]]; then
  exec "$FAKE_PYTHON" -m reefproof.cli menu
fi
if [[ "${FAKE_UV_EXEC_HELP:-0}" == "1" && " $* " == *" reefproof --help "* ]]; then
  exec "$FAKE_PYTHON" -m reefproof.cli --help
fi
if [[ " $* " == *" reefproof doctor "* ]]; then
  exit 19
fi
printf 'FAKE UV: %s\\n' "$*"
""",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_directory}{os.pathsep}{environment['PATH']}",
            "FAKE_PYTHON": sys.executable,
            "FAKE_UV_LOG": str(uv_log),
            "REEFPROOF_ENV": "dev",
            "REEFPROOF_DATA_DIRECTORY": str(tmp_path / "data"),
            "REEFPROOF_HISTORY_FILE": str(history),
            "TERM": "dumb",
        }
    )
    return environment, uv_log, history


def test_root_launcher_is_executable_and_selects_dev_or_prod() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")

    assert LAUNCHER.stat().st_mode & 0o111
    assert subprocess.run(["bash", "-n", str(LAUNCHER)], check=False).returncode == 0
    assert 'environment="${REEFPROOF_ENV:-' in source
    assert "dev|development)" in source
    assert "prod|production)" in source
    assert 'launcher=(uv run --project "$repository_root" reefproof)' in source
    assert 'binary="$repository_root/dist/reefproof"' in source
    assert 'launcher=("$binary")' in source
    assert 'exec "${launcher[@]}" "$@"' in source
    assert 'exec "${launcher[@]}" menu' in source


def test_root_launcher_tty_menu_lifecycle_routes_palette_and_exits(tmp_path: Path) -> None:
    environment, uv_log, history = _fake_uv_environment(tmp_path)
    terminal = _spawn_pty([str(LAUNCHER.resolve())], environment)
    try:
        menu_output = terminal.expect("Exit ReefProof")
        assert "System status" in menu_output
        assert "Open workbench" in menu_output
        terminal.send(b"3")
        terminal.expect("exit status 19")
        terminal.send(b"\r")
        terminal.expect("Exit ReefProof")
        terminal.send(b"4")
        terminal.expect("Status — inspect")
        terminal.send(b"1")
        terminal.expect("FAKE UV")
        terminal.send(b"\r")
        terminal.expect("Back")
        terminal.send(b"6")
        terminal.expect("Exit ReefProof")
        terminal.send(b"2")
        palette_output = terminal.expect("more matches")
        assert "reefproof>" in palette_output
        terminal.send(b"explain\r")
        terminal.expect("input>")
        terminal.send(b"RP-1\r")
        terminal.expect("Running…")
        terminal.expect("exit status 0")
        terminal.send(b"\r")
        terminal.expect("reefproof>")
        terminal.send(b"snapshot --hydros-export=\r")
        terminal.expect("input>")
        terminal.send(b"\x03")
        terminal.expect("reefproof>")
        terminal.send(b"vers\r")
        terminal.expect("$ reefproof version")
        terminal.expect("exit status 0")
        terminal.send(b"\r")
        terminal.expect("reefproof>")
        terminal.send(b"back\r")
        terminal.expect("System: DEV")
        terminal.send(b"8")
        terminal.read_to_exit()
    finally:
        terminal.close()

    assert [line.split("\t", 1)[1] for line in history.read_text().splitlines()] == [
        "doctor",
        "status",
        "explain RP-1",
        "version",
    ]
    assert any("reefproof menu" in line for line in uv_log.read_text().splitlines())


def test_root_launcher_preserves_explicit_status_and_non_tty_help(tmp_path: Path) -> None:
    environment, uv_log, history = _fake_uv_environment(tmp_path)

    explicit = subprocess.run(
        [str(LAUNCHER.resolve()), "doctor"],
        capture_output=True,
        check=False,
        env=environment,
    )
    redirected = subprocess.run(
        [str(LAUNCHER.resolve())],
        capture_output=True,
        check=False,
        env=environment,
    )

    assert explicit.returncode == 19
    assert redirected.returncode == 0
    assert [line.split("\t", 1)[1] for line in history.read_text().splitlines()] == [
        "doctor",
        "--help",
    ]
    assert any("reefproof --help" in line for line in uv_log.read_text().splitlines())


def test_root_launcher_renders_rich_help_on_stdout_tty(tmp_path: Path) -> None:
    environment, _, _ = _fake_uv_environment(tmp_path)
    environment.update(
        {
            "REEFPROOF_DATA_DIRECTORY": str(tmp_path / "data"),
            "REEFPROOF_HISTORY_FILE": str(tmp_path / "history.log"),
            "TERM": "xterm-256color",
            "FAKE_UV_EXEC_HELP": "1",
        }
    )
    environment.pop("NO_COLOR", None)

    terminal = _spawn_pty([str(LAUNCHER.resolve()), "--help"], environment)
    try:
        rich_output = terminal.read_to_exit()
    finally:
        terminal.close()

    assert terminal.process.returncode == 0
    assert "╭" in rich_output
