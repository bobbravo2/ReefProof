from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from reefproof.cli import app
from reefproof.service.lifecycle import DaemonState, PidStatus
from reefproof.service.workbench import EndpointState
from reefproof.settings import ApiSettings, Settings

runner = CliRunner()


def test_hydros_check_persists_operator_confirmed_fahrenheit_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(tmp_path / "evidence"))
    result = runner.invoke(
        app,
        [
            "hydros-check",
            "--hydros-export",
            "tests/fixtures/configuration/hydros-download-config-sanitized.json",
            "--captured-at",
            "2026-07-31T19:45:00-04:00",
            "--expected-temperature-unit",
            "fahrenheit",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "PASS INFO RP-UNIT-001" in result.stdout
    assert '$.Option["Option"].tempFmt = "1"' in result.stdout
    assert "Snapshot persisted:" in result.stdout
    assert "Evaluation persisted:" in result.stdout


def test_hydros_check_emits_structured_release_parity_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(tmp_path / "evidence"))
    result = runner.invoke(
        app,
        [
            "hydros-check",
            "--hydros-export",
            "tests/fixtures/configuration/hydros-download-config-sanitized.json",
            "--captured-at",
            "2026-07-31T19:45:00-04:00",
            "--expected-temperature-unit",
            "fahrenheit",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    document = json.loads(result.stdout)
    assert document["invariant_id"] == "RP-UNIT-001"
    assert document["state"] == "PASS"
    assert document["severity"] == "info"
    assert document["snapshot_hash"].startswith("sha256:")
    assert document["evidence"] == ['$.Option["Option"].tempFmt = "1"']


def test_version_reports_build_identity() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert "ReefProof 0.1.2" in result.stdout
    assert "Python 3.13" in result.stdout
    assert "Git commit:" in result.stdout
    assert "Build state:" in result.stdout
    assert "Build source:" in result.stdout
    assert "Build created:" in result.stdout


def test_version_works_outside_git_checkout(tmp_path: Path) -> None:
    original = Path.cwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(app, ["version"])
    finally:
        os.chdir(original)

    assert result.exit_code == 0
    assert "Git commit: UNKNOWN" in result.stdout
    assert "Build state: unknown" in result.stdout


def test_version_works_without_git(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_git(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr("reefproof.cli.subprocess.run", missing_git)
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert "Git commit: UNKNOWN" in result.stdout
    assert "Build state: unknown" in result.stdout


def test_packaged_version_uses_embedded_identity_not_working_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reefproof import cli

    monkeypatch.setattr(cli, "BUILD_REVISION", "a" * 40)
    monkeypatch.setattr(cli, "BUILD_SOURCE", "https://example.invalid/ReefProof")
    monkeypatch.setattr(cli, "BUILD_CREATED", "2026-07-25T15:31:40-04:00")

    def unexpected_git(*args: object, **kwargs: object) -> None:
        raise AssertionError("packaged identity consulted Git")

    monkeypatch.setattr(cli.subprocess, "run", unexpected_git)
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert f"Git commit: {'a' * 40}" in result.stdout
    assert "Build state: packaged" in result.stdout
    assert "Build source: https://example.invalid/ReefProof" in result.stdout


def test_healthy_doctor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(tmp_path))
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "PASS: Python version" in result.stdout
    assert "PASS: HYDROS transport — not installed" in result.stdout
    assert "SQLite evidence store" in result.stdout
    assert "Workbench process" in result.stdout
    assert "usage ledger" not in result.stdout
    assert "Doctor result: 0 failure(s)" in result.stdout


def test_workbench_status_reports_running(monkeypatch: pytest.MonkeyPatch) -> None:
    from reefproof import cli

    class Response:
        status = 200

        def read(self) -> bytes:
            return json.dumps(
                {
                    "version": "0.1.0",
                    "operating_mode": "watch",
                    "readiness": "degraded",
                    "monitoring_confidence": "degraded",
                }
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(cli, "load_settings", lambda create_data_directory=False: Settings())
    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout: Response())
    # Mock daemon as running so managed status is MANAGED
    mock_daemon = PidStatus(state=DaemonState.RUNNING, pid=12345)

    def mock_lifecycle_status(self):
        return mock_daemon

    monkeypatch.setattr("reefproof.service.workbench.DaemonLifecycle.status", mock_lifecycle_status)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert result.stdout == (
        "PASS: ReefProof workbench is reachable\n"
        "URL: http://127.0.0.1:8787/workbench\n"
        "Process ownership: MANAGED\n"
        "Observed mode: watch\n"
        "Assurance readiness: DEGRADED\n"
        "Monitoring confidence: DEGRADED\n"
    )

    strict = runner.invoke(app, ["status", "--require-ready"])
    assert strict.exit_code == 1
    assert "Assurance readiness: DEGRADED" in strict.stdout


def test_workbench_status_reports_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    from reefproof import cli

    monkeypatch.setattr(cli, "load_settings", lambda create_data_directory=False: Settings())

    def refused(url: str, timeout: float):
        raise ConnectionRefusedError

    monkeypatch.setattr("urllib.request.urlopen", refused)
    monkeypatch.setattr("reefproof.service.workbench._port_is_open", lambda *args: False)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 1
    assert result.stdout == (
        "FAIL: ReefProof workbench is not reachable\n"
        "URL: http://127.0.0.1:8787/workbench\n"
        "Configured mode: fixture\n"
        "Start: ./reefproof serve --no-open\n"
    )


def test_workbench_status_rejects_non_reefproof_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reefproof import cli

    class Response:
        status = 200

        def read(self) -> bytes:
            return b'{"status":"ok"}'

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(cli, "load_settings", lambda create_data_directory=False: Settings())
    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout: Response())

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 1
    assert "FAIL: endpoint did not return ReefProof status" in result.stdout
    assert "Configured mode: fixture" in result.stdout


def test_redirected_help_uses_plain_formatter() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Usage: root [OPTIONS] COMMAND [ARGS]..." in result.stdout
    assert "Commands:" in result.stdout
    assert "╭" not in result.stdout


@pytest.mark.parametrize(
    "variable",
    ["REEFPROOF_HOME_ASSISTANT_TOKEN", "REEFPROOF_BOOTSTRAP_SECRET"],
)
def test_doctor_accepts_supported_token_without_disclosing_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    variable: str,
) -> None:
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(tmp_path))
    token = "private-test-token"
    monkeypatch.setenv(variable, token)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert f"supported secret configured: {variable}" in result.stdout
    assert token not in result.stdout


def test_doctor_rejects_unknown_secret_like_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REEFPROOF_VENDOR_PASSWORD", "private-test-password")

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "unsupported keys: REEFPROOF_VENDOR_PASSWORD" in result.stdout
    assert "private-test-password" not in result.stdout


def test_doctor_failure_reporting(monkeypatch: pytest.MonkeyPatch) -> None:
    from reefproof import cli
    from reefproof.doctor import Check

    monkeypatch.setattr(cli, "run_checks", lambda: [Check("FAIL", "example", "broken")])
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "FAIL: example — broken" in result.stdout
    assert "Doctor result: 1 failure(s)" in result.stdout


def test_doctor_accepts_an_installed_distribution_without_a_source_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import reefproof.doctor as doctor_module

    installed_module = tmp_path / "site-packages" / "reefproof" / "doctor.py"
    monkeypatch.setattr(doctor_module, "__file__", str(installed_module))
    checks = doctor_module.run_checks()

    structure = next(check for check in checks if check.name == "repository structure")
    assert structure.status == "PASS"
    assert "installed distribution" in structure.detail


def test_serve_opens_workbench_after_server_start_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reefproof import cli

    runtime = SimpleNamespace(settings=Settings())
    opened: list[str] = []

    monkeypatch.setattr(cli, "build_runtime", lambda settings: runtime)
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url) or True)

    def run_api(
        runtime_value: object,
        *,
        on_started: object,
        reload: bool,
        runtime_factory: object,
    ) -> None:
        assert runtime_value is runtime
        assert callable(on_started)
        assert reload is True
        assert callable(runtime_factory)
        on_started()

    monkeypatch.setattr(cli, "run_api", run_api)

    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 0, result.stdout
    assert opened == ["http://127.0.0.1:8787/workbench"]
    assert "ReefProof local workbench: http://127.0.0.1:8787/workbench" in result.stdout
    assert "Evidence provenance: MANUAL / NOT LIVE" in result.stdout
    assert "Operator runtime settings:" in result.stdout
    assert "environment=development" in result.stdout
    assert "bind=127.0.0.1" in result.stdout
    assert "port=8787" in result.stdout
    assert "active_project_id=primary-reef-system" in result.stdout
    assert "log_level=INFO" in result.stdout
    assert "json_logs=disabled" in result.stdout
    assert "reload_watcher=enabled" in result.stdout
    assert "bootstrap_secret=generated-per-start" in result.stdout
    assert 'Access log format: <level> <client> - "<request>" <status>' in result.stdout


def test_serve_no_open_starts_without_launching_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reefproof import cli

    runtime = SimpleNamespace(settings=Settings(api=ApiSettings(bind="::1", port=9876)))
    monkeypatch.setattr(cli, "build_runtime", lambda settings: runtime)
    monkeypatch.setattr(
        cli.webbrowser,
        "open",
        lambda url: pytest.fail(f"unexpected browser launch: {url}"),
    )

    def run_api(
        runtime_value: object,
        *,
        on_started: object,
        reload: bool,
        runtime_factory: object,
    ) -> None:
        assert runtime_value is runtime
        assert on_started is None
        assert reload is True
        assert callable(runtime_factory)

    monkeypatch.setattr(cli, "run_api", run_api)

    result = runner.invoke(app, ["serve", "--no-open"])

    assert result.exit_code == 0, result.stdout
    assert "http://[::1]:9876/workbench" in result.stdout


def test_serve_keyboard_interrupt_stops_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reefproof import cli

    runtime = SimpleNamespace(settings=Settings())
    monkeypatch.setattr(cli, "build_runtime", lambda settings: runtime)

    def interrupt(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_api", interrupt)

    result = runner.invoke(app, ["serve", "--no-open"])

    assert result.exit_code == 0, result.stdout
    assert "Stopped ReefProof local workbench." in result.stdout


def test_serve_explicit_bind_and_port_enable_container_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reefproof import cli

    observed: list[Settings] = []

    def build_runtime(settings: Settings) -> SimpleNamespace:
        observed.append(settings)
        return SimpleNamespace(settings=settings)

    monkeypatch.setattr(cli, "build_runtime", build_runtime)
    monkeypatch.setattr(cli, "run_api", lambda runtime_value, **kwargs: None)

    result = runner.invoke(
        app,
        ["serve", "--bind", "0.0.0.0", "--port", "8787", "--no-open"],
    )

    assert result.exit_code == 0, result.stdout
    assert observed[0].api.bind == "0.0.0.0"
    assert observed[0].api.port == 8787
    assert observed[0].api.allow_non_loopback is True
    assert "http://0.0.0.0:8787/workbench" in result.stdout


def test_serve_project_id_override_is_passed_to_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reefproof import cli

    observed: list[Settings] = []

    def build_runtime(settings: Settings) -> SimpleNamespace:
        observed.append(settings)
        return SimpleNamespace(settings=settings)

    monkeypatch.setattr(cli, "build_runtime", build_runtime)
    monkeypatch.setattr(cli, "run_api", lambda runtime_value, **kwargs: None)

    result = runner.invoke(
        app,
        ["serve", "--project-id", "legacy-reef-system", "--no-open"],
    )

    assert result.exit_code == 0, result.stdout
    assert observed[0].project.project_id == "legacy-reef-system"
    assert "active_project_id=legacy-reef-system" in result.stdout


def test_serve_production_always_disables_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reefproof import cli

    runtime = SimpleNamespace(settings=Settings())
    monkeypatch.setenv("REEFPROOF_ENVIRONMENT", "production")
    monkeypatch.setattr(cli, "build_runtime", lambda settings: runtime)

    def run_api(
        runtime_value: object,
        *,
        on_started: object,
        reload: bool,
        runtime_factory: object,
    ) -> None:
        assert runtime_value is runtime
        assert reload is False

    monkeypatch.setattr(cli, "run_api", run_api)

    result = runner.invoke(app, ["serve", "--no-open", "--reload"])

    assert result.exit_code == 0, result.stdout
    assert "environment=production" in result.stdout
    assert "reload_watcher=disabled" in result.stdout


def test_serve_development_can_disable_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reefproof import cli

    runtime = SimpleNamespace(settings=Settings())
    monkeypatch.setattr(cli, "build_runtime", lambda settings: runtime)
    observed: list[bool] = []
    monkeypatch.setattr(
        cli,
        "run_api",
        lambda runtime_value, **kwargs: observed.append(kwargs["reload"]),
    )

    result = runner.invoke(app, ["serve", "--no-open", "--no-reload"])

    assert result.exit_code == 0, result.stdout
    assert observed == [False]


def test_daemon_start_uses_detached_lifecycle_interface(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from reefproof import cli
    from reefproof.service.lifecycle import DaemonState, PidStatus

    class FakeLifecycle:
        pid_file = tmp_path / "reefproof.pid"
        log_file = tmp_path / "reefproof.log"
        current = PidStatus(DaemonState.STOPPED)

        def status(self) -> PidStatus:
            return self.current

        def start(self, command: tuple[str, ...]) -> PidStatus:
            assert command == (
                "reefproof",
                "serve",
                "--no-open",
                "--no-reload",
                "--project-id",
                "legacy-reef-system",
            )
            self.current = PidStatus(DaemonState.RUNNING, pid=4321)
            return self.current

        def stop(self, *, timeout_seconds: float) -> PidStatus:
            self.current = PidStatus(DaemonState.STOPPED)
            return self.current

    lifecycle = FakeLifecycle()
    monkeypatch.setattr(cli, "_daemon_lifecycle", lambda **kwargs: lifecycle)
    monkeypatch.setattr(
        cli,
        "_daemon_command",
        lambda project_id: (
            "reefproof",
            "serve",
            "--no-open",
            "--no-reload",
            "--project-id",
            project_id,
        ),
    )
    observations = iter(
        (
            SimpleNamespace(endpoint=EndpointState.STOPPED, managed=False),
            SimpleNamespace(endpoint=EndpointState.REEFPROOF, managed=True),
        )
    )
    monkeypatch.setattr(
        "reefproof.cli_domains.runtime.observe_workbench",
        lambda *args, **kwargs: next(observations),
    )

    result = runner.invoke(app, ["daemon", "start", "--project-id", "legacy-reef-system"])

    assert result.exit_code == 0, result.stdout
    assert "Started ReefProof daemon (PID 4321)." in result.stdout
    assert str(lifecycle.pid_file) in result.stdout
    assert str(lifecycle.log_file) in result.stdout


def test_daemon_stop_reports_idempotent_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    from reefproof import cli
    from reefproof.service.lifecycle import DaemonState, PidStatus

    class FakeLifecycle:
        pid_file = Path(".local/data/reefproof.pid")

        def stop(self, *, timeout_seconds: float) -> PidStatus:
            assert timeout_seconds == 2.5
            return PidStatus(DaemonState.STOPPED)

    monkeypatch.setattr(cli, "_daemon_lifecycle", lambda **kwargs: FakeLifecycle())

    result = runner.invoke(app, ["daemon", "stop", "--timeout", "2.5"])

    assert result.exit_code == 0, result.stdout
    assert "daemon stopped" in result.stdout


def test_daemon_restart_refuses_to_signal_an_unowned_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reefproof import cli

    class FakeLifecycle:
        pid_file = Path(".local/data/reefproof.pid")

        def status(self) -> PidStatus:
            return PidStatus(DaemonState.STOPPED)

    monkeypatch.setattr(cli, "_daemon_lifecycle", lambda **kwargs: FakeLifecycle())

    result = runner.invoke(app, ["daemon", "restart"])

    assert result.exit_code == 1
    assert "no running managed daemon" in result.stderr


def test_daemon_status_reports_running_and_stopped_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reefproof import cli
    from reefproof.service.lifecycle import DaemonState, PidStatus

    class FakeLifecycle:
        pid_file = Path(".local/data/reefproof.pid")
        current = PidStatus(DaemonState.RUNNING, pid=4321)

        def status(self) -> PidStatus:
            return self.current

    lifecycle = FakeLifecycle()
    monkeypatch.setattr(cli, "_daemon_lifecycle", lambda **kwargs: lifecycle)
    running = runner.invoke(app, ["daemon", "status"])
    assert running.exit_code == 0, running.stdout
    assert "running (PID 4321)" in running.stdout

    lifecycle.current = PidStatus(DaemonState.STOPPED)
    stopped = runner.invoke(app, ["daemon", "status"])
    assert stopped.exit_code == 1
    assert "daemon is stopped" in stopped.stdout


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (("--help",), "offline by default"),
        (("version", "--help"), "build identity"),
        (("doctor", "--help"), "network access"),
        (("serve", "--help"), "loopback-only local assurance workbench"),
        (("snapshot", "--help"), "deterministic snapshot evidence"),
        (("graph", "--help"), "reliability relationships"),
        (("check", "--help"), "safety invariants"),
        (("explain", "--help"), "registered invariant"),
        (("infra-smoke", "--help"), "network-free evidence-store"),
        (("daemon", "--help"), "PID file"),
        (("daemon", "start", "--help"), "detached"),
        (("daemon", "stop", "--help"), "graceful shutdown"),
        (("daemon", "status", "--help"), "running, stopped, stale"),
        (("database", "--help"), "durable evidence storage"),
        (("database", "schema", "--help"), "SQLite schema"),
        (("database", "verify", "--help"), "SQLite integrity"),
        (("database", "inspect", "--help"), "fixed evidence projections"),
        (("database", "backup", "--help"), "SQLite-consistent backup"),
        (("database", "restore", "--help"), "verified backup"),
        (("auth", "--help"), "operator authentication"),
        (("auth", "sessions", "--help"), "authenticated operator browser sessions"),
        (("auth", "revoke-session", "--help"), "explicit selection"),
        (("auth", "totp", "--help"), "operator phone authenticator"),
        (("auth", "totp", "reset", "--help"), "authority reset"),
    ],
)
def test_every_cli_command_has_operator_help(arguments: tuple[str, ...], expected: str) -> None:
    result = runner.invoke(app, list(arguments))

    assert result.exit_code == 0, result.stdout
    assert "Usage:" in result.stdout
    assert expected in " ".join(result.stdout.split())


def test_serve_rejects_unknown_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REEFPROOF_ENVIRONMENT", "staging")

    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 2
    assert "must be development or production" in result.stderr


@pytest.mark.parametrize("command", ["start", "history", "storage"])
def test_retired_commands_fail(command: str) -> None:
    result = runner.invoke(app, [command])

    assert result.exit_code == 2


def test_auth_sessions_lists_active_operator_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    from reefproof import cli
    from reefproof.api.sessions import ActiveSession

    class FakeSessions:
        def active_sessions(self) -> tuple[ActiveSession, ...]:
            return (
                ActiveSession(
                    session_id="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee1111",
                    principal_id="acceptance-authority",
                    issued_at=1,
                ),
            )

    monkeypatch.setattr(cli, "_session_operator", lambda: FakeSessions())

    result = runner.invoke(app, ["auth", "sessions"])

    assert result.exit_code == 0, result.stdout
    assert "Active authenticated operator sessions:" in result.stdout
    assert "session=eeee1111" in result.stdout
    assert "principal=acceptance-authority" in result.stdout
    assert "id=aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee1111" in result.stdout


def test_auth_revoke_session_interactive_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    from reefproof import cli
    from reefproof.api.sessions import ActiveSession

    class FakeSessions:
        def __init__(self) -> None:
            self.revoked: list[str] = []

        def active_sessions(self) -> tuple[ActiveSession, ...]:
            return (
                ActiveSession(
                    session_id="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee1111",
                    principal_id="acceptance-authority",
                    issued_at=1,
                ),
                ActiveSession(
                    session_id="bbbbbbbb-cccc-4ddd-8eee-ffffffff2222",
                    principal_id="acceptance-authority",
                    issued_at=2,
                ),
            )

        def revoke_session_id(self, session_id: str) -> bool:
            self.revoked.append(session_id)
            return True

    fake_sessions = FakeSessions()
    monkeypatch.setattr(cli, "_session_operator", lambda: fake_sessions)

    result = runner.invoke(app, ["auth", "revoke-session"], input="2\n")

    assert result.exit_code == 0, result.stdout
    assert fake_sessions.revoked == ["bbbbbbbb-cccc-4ddd-8eee-ffffffff2222"]
    assert "Revoked operator session bbbbbbbb-cccc-4ddd-8eee-ffffffff2222." in result.stdout


def test_auth_revoke_session_direct_id_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    from reefproof import cli
    from reefproof.api.sessions import ActiveSession

    class FakeSessions:
        def active_sessions(self) -> tuple[ActiveSession, ...]:
            return (
                ActiveSession(
                    session_id="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee1111",
                    principal_id="acceptance-authority",
                    issued_at=1,
                ),
            )

        def revoke_session_id(self, session_id: str) -> bool:
            return session_id == "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee1111"

    monkeypatch.setattr(cli, "_session_operator", lambda: FakeSessions())

    invalid = runner.invoke(app, ["auth", "revoke-session", "--session-id", "missing-session-id"])
    assert invalid.exit_code != 0
    assert "Session ID is not active" in invalid.stderr

    valid = runner.invoke(
        app,
        ["auth", "revoke-session", "--session-id", "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee1111"],
    )
    assert valid.exit_code == 0, valid.stdout
    assert "Revoked operator session aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee1111." in valid.stdout


def test_serve_reports_runtime_construction_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reefproof import cli

    def fail_runtime(settings: Settings) -> None:
        raise ValueError("api.bind must be loopback-only")

    monkeypatch.setattr(cli, "build_runtime", fail_runtime)
    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 2
    assert "FAIL: could not start local workbench" in result.stderr
    assert "loopback-only" in result.stderr


def test_serve_help_documents_default_browser_and_headless_mode() -> None:
    result = runner.invoke(app, ["serve", "--help"])

    assert result.exit_code == 0
    assert "--open" in result.stdout
    assert "--no-open" in result.stdout
    assert "--reload" in result.stdout
    assert "--no-reload" in result.stdout
    assert "default browser" in result.stdout
    assert "loopback-only local assurance workbench" in result.stdout


def test_phase_zero_commands_do_not_open_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    monkeypatch.setattr(
        "reefproof.doctor.observe_workbench",
        lambda settings, lifecycle: SimpleNamespace(
            daemon=SimpleNamespace(state=DaemonState.STOPPED),
            endpoint=EndpointState.STOPPED,
            managed=False,
        ),
    )

    for command in ("version", "doctor"):
        result = runner.invoke(app, [command])
        assert result.exit_code == 0, result.stdout


def test_phase_zero_commands_do_not_record_conversation_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(tmp_path))
    for command in ("version", "doctor"):
        result = runner.invoke(app, [command])
        assert result.exit_code == 0
        lowered = result.stdout.lower()
        assert "prompt" not in lowered
        assert "response" not in lowered


def test_snapshot_command_prints_deterministic_json() -> None:
    result = runner.invoke(
        app,
        ["snapshot", "--fixture", "tests/fixtures/configuration/authored-minimal.json"],
    )

    assert result.exit_code == 0, result.stdout
    document = json.loads(result.stdout)
    assert document["snapshot_version"] == "0.1"
    assert document["provenance"] == "AUTHORED"
    assert len(document["entities"]) == 2
    assert len(document["authored_entities"]) == 1
    assert document["configuration_hash"].startswith("sha256:")


def test_snapshot_command_writes_explicit_output(tmp_path: Path) -> None:
    output = tmp_path / "snapshot.json"

    result = runner.invoke(
        app,
        [
            "snapshot",
            "--fixture",
            "tests/fixtures/configuration/authored-minimal.json",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert output.is_file()
    assert "Wrote canonical snapshot:" in result.stdout
    assert "Configuration hash: sha256:" in result.stdout
    assert "WARNING: One or more observed entities have unknown confidence." in result.stdout


def test_snapshot_command_imports_offline_hydros_export(tmp_path: Path) -> None:
    output = tmp_path / "hydros.snapshot.json"
    result = runner.invoke(
        app,
        [
            "snapshot",
            "--hydros-export",
            "tests/fixtures/configuration/hydros-download-config-sanitized.json",
            "--captured-at",
            "2026-07-31T19:45:00-04:00",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["provenance"] == "OBSERVED"
    assert document["source_format"] == "hydros_chrome_download_config"
    assert "HYDROS field semantics and relationships are unverified" in result.stdout


def test_snapshot_command_never_overwrites_original_hydros_export(tmp_path: Path) -> None:
    export = tmp_path / "original.json"
    original = Path(
        "tests/fixtures/configuration/hydros-download-config-sanitized.json"
    ).read_bytes()
    export.write_bytes(original)

    result = runner.invoke(
        app,
        [
            "snapshot",
            "--hydros-export",
            str(export),
            "--captured-at",
            "2026-07-31T19:45:00-04:00",
            "--output",
            str(export),
        ],
    )

    assert result.exit_code == 2
    assert "must not overwrite the" in result.stderr
    assert "original HYDROS export" in result.stderr
    assert export.read_bytes() == original


def test_graph_command_explains_correlated_redundancy() -> None:
    result = runner.invoke(
        app,
        [
            "graph",
            "--fixture",
            "tests/fixtures/configuration/unsafe-correlated-returns.json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "2 observed, 1 authored" in result.stdout
    assert "Return A and Return B share Example Shared Power Domain" in result.stdout
    assert "not an invariant safety evaluation" in result.stdout


def test_check_command_reports_critical_failure_and_exit_code() -> None:
    result = runner.invoke(
        app,
        [
            "check",
            "--fixture",
            "tests/fixtures/configuration/unsafe-correlated-returns.json",
        ],
    )

    assert result.exit_code == 40
    assert "FAIL CRITICAL RP-CIRC-001" in result.stdout
    assert "Return A and Return B" in result.stdout
    assert "Operator action:" in result.stdout


def test_check_command_emits_complete_json() -> None:
    result = runner.invoke(
        app,
        [
            "check",
            "--fixture",
            "tests/fixtures/configuration/unsafe-correlated-returns.json",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 40
    document = json.loads(result.stdout)
    result_document = document["results"][0]
    assert result_document["state"] == "FAIL"
    assert result_document["invariant_id"] == "RP-CIRC-001"
    assert result_document["policy_hash"].startswith("sha256:")
    assert result_document["recommended_operator_action"]


def test_explain_command_describes_pass_fail_and_unknown() -> None:
    result = runner.invoke(app, ["explain", "RP-CIRC-001"])

    assert result.exit_code == 0
    assert "Protects:" in result.stdout
    assert "PASS:" in result.stdout
    assert "FAIL:" in result.stdout
    assert "UNKNOWN:" in result.stdout
