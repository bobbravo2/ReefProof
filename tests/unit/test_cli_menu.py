from __future__ import annotations

import asyncio
import os
from typing import cast

from prompt_toolkit.application import create_app_session
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.key_binding import KeyPressEvent
from prompt_toolkit.output import DummyOutput

from reefproof.api.sessions import SESSION_MAX_AGE_SECONDS
from reefproof.cli_domains import menu
from reefproof.storage import Database


def test_console_is_one_full_screen_ansi_application_with_main_focus() -> None:
    console = menu.ConsoleController()

    assert console.app.full_screen is True
    assert console.app.color_depth.name == "DEPTH_4_BIT"
    assert console.view == "main"
    assert console.app.layout.current_control is console.menu_control


def test_console_view_transitions_focus_the_active_control() -> None:
    console = menu.ConsoleController()

    console.show_workbench_choice()
    assert console.view == "serve-choice"
    assert console.app.layout.current_control is console.menu_control
    console.show_palette()
    assert console.view == "palette"
    assert console.app.layout.current_control is console.palette_control
    console.show_results("output")
    assert console.view == "results"
    assert console.app.layout.current_control is console.results_control
    console.show_main()
    assert console.view == "main"
    assert console.app.layout.current_control is console.menu_control


def test_main_menu_includes_workbench_status_and_safety_header() -> None:
    assert "LOCAL ASSURANCE CONSOLE" in menu.MAIN_MENU_MESSAGE
    assert any(key == "manage" and "start, stop" in label for key, label in menu.MAIN_OPTIONS)
    assert any(key == "backup" and "backed-up storage" in label for key, label in menu.MAIN_OPTIONS)
    assert any(key == "desktop" and "remote-hosted" in label for key, label in menu.MAIN_OPTIONS)
    assert all(key != "help" for key, _ in menu.MAIN_OPTIONS)
    assert all(
        any(ord(character) > 10_000 for character in label) for _, label in menu.MAIN_OPTIONS
    )
    assert "never control" in menu.SAFETY_HEADER


def test_main_menu_formats_title_and_safety_boundary_without_literal_markup() -> None:
    console = menu.ConsoleController()

    fragments = console._menu_text()
    rendered = "".join(fragment[1] for fragment in fragments)

    assert "<b>" not in rendered
    assert "Choose a safe, read-only operator workflow.\n" in rendered
    assert "Observe, model, challenge, alert — never control.\n" in rendered


def test_main_menu_reports_owned_status_and_refreshes_when_reentered() -> None:
    observations = iter(
        (
            menu.MenuSystemStatus("DEV", "STOPPED", None, ("CONSOLE",), 0),
            menu.MenuSystemStatus("DEV", "RUNNING", 4321, ("CONSOLE",), 2),
        )
    )
    console = menu.ConsoleController(system_status_provider=lambda _: next(observations))

    assert "System: DEV • daemon STOPPED • apps CONSOLE • sessions 0 LIVE" in "".join(
        fragment[1] for fragment in console._menu_text()
    )

    console.show_main()

    assert "System: DEV • daemon RUNNING (PID 4321) • apps CONSOLE • sessions 2 LIVE" in "".join(
        fragment[1] for fragment in console._menu_text()
    )


def test_main_menu_reserves_the_wrap_column_at_narrow_terminal_width() -> None:
    status = menu.MenuSystemStatus("DEV", "RUNNING", 4321, ("CONSOLE",), 2)
    console = menu.ConsoleController(
        system_status_provider=lambda _: status,
        terminal_width_provider=lambda: 60,
    )

    rendered = "".join(fragment[1] for fragment in console._menu_text())
    lines = rendered.splitlines()

    assert "System: DEV • daemon RUNNING (PID 4321)" in lines
    assert "Owned: apps CONSOLE • sessions 2 LIVE" in lines
    assert any(line.endswith("…") for line in lines)
    assert all(menu.get_cwidth(line) <= 59 for line in lines)
    assert menu.get_cwidth(console._footer_text()) <= 59


def test_main_menu_labels_begin_in_one_column_after_variable_width_icons() -> None:
    status = menu.MenuSystemStatus("DEV", "STOPPED", None, ("CONSOLE",), 0)
    console = menu.ConsoleController(
        system_status_provider=lambda _: status,
        terminal_width_provider=lambda: 100,
    )
    option_lines = [
        fragment[1].rstrip("\n")
        for fragment in console._menu_text()
        if any(
            label in fragment[1]
            for label in ("System status", "Command palette", "Desktop Workbench")
        )
    ]

    label_columns = {
        menu.get_cwidth(line[: line.index(label)])
        for line, label in zip(
            option_lines,
            ("System status", "Command palette", "Desktop Workbench"),
            strict=True,
        )
    }

    assert label_columns == {9}


def test_menu_status_observes_only_owned_processes_and_unexpired_sessions(
    monkeypatch, tmp_path
) -> None:
    class ProcessState:
        foreground_process: object | None = None
        desktop_process: object | None = object()

    now = 2_000_000_000
    data_directory = tmp_path / "data"
    data_directory.mkdir()
    (data_directory / "reefproof.pid").write_text(f"{os.getpid()}\n")
    database = Database(data_directory / "reefproof.sqlite3")
    database.migrate()
    for session_id, issued_at in (
        ("live-session", now - 60),
        ("expired-session", now - SESSION_MAX_AGE_SECONDS - 1),
    ):
        database.record_operator_session(
            project_id="primary-reef-system",
            session_id=session_id,
            principal_id="local-acceptance-authority",
            issued_at=issued_at,
            authentication_generation=0,
        )
    monkeypatch.setenv("REEFPROOF_ENVIRONMENT", "production")
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(data_directory))
    monkeypatch.setattr(menu.time, "time", lambda: now)

    status = menu._observe_menu_system_status(ProcessState())

    assert status == menu.MenuSystemStatus(
        environment="PROD",
        daemon_state="RUNNING",
        daemon_pid=os.getpid(),
        owned_apps=("CONSOLE", "DESKTOP"),
        live_sessions=1,
    )


def test_desktop_menu_launches_repository_owned_command(monkeypatch, tmp_path) -> None:
    class Process:
        returncode = 0
        pid = 123

        async def communicate(self):
            return b"desktop started\n", b""

    observed = {}

    async def fake_exec(*args, **kwargs):
        observed["args"] = args
        observed["cwd"] = kwargs["cwd"]
        return Process()

    launcher = tmp_path / "reefproof"
    launcher.write_text("launcher")
    (tmp_path / "package.json").write_text("{}")
    monkeypatch.setenv("REEFPROOF_MENU_LAUNCHER", str(launcher))
    monkeypatch.setattr(menu.asyncio, "create_subprocess_exec", fake_exec)
    console = menu.ConsoleController()

    asyncio.run(console._run_desktop())

    assert observed == {"args": ("make", "run/desktop"), "cwd": tmp_path}
    assert "desktop started" in console.result_text


def test_desktop_menu_launches_remote_mode_without_local_fallback(monkeypatch, tmp_path) -> None:
    class Process:
        returncode = 0
        pid = 124

        async def communicate(self):
            return b"remote desktop started\n", b""

    observed = {}

    async def fake_exec(*args, **kwargs):
        observed["args"] = args
        observed["env"] = kwargs["env"]
        return Process()

    launcher = tmp_path / "reefproof"
    launcher.write_text("launcher")
    (tmp_path / "package.json").write_text("{}")
    monkeypatch.setenv("REEFPROOF_MENU_LAUNCHER", str(launcher))
    monkeypatch.setenv("REEFPROOF_REMOTE_ORIGIN", "http://192.168.1.20:8787")
    monkeypatch.setattr(menu.asyncio, "create_subprocess_exec", fake_exec)
    console = menu.ConsoleController()

    asyncio.run(console._run_desktop("remote-hosted"))

    assert observed["args"] == ("make", "run/desktop")
    assert observed["env"]["REEFPROOF_DESKTOP_MODE"] == "remote-hosted"
    assert observed["env"]["REEFPROOF_REMOTE_ORIGIN"] == "http://192.168.1.20:8787"
    assert "Mode: remote-hosted" in console.result_text


def test_desktop_menu_requires_explicit_remote_origin(monkeypatch, tmp_path) -> None:
    launcher = tmp_path / "reefproof"
    launcher.write_text("launcher")
    (tmp_path / "package.json").write_text("{}")
    monkeypatch.setenv("REEFPROOF_MENU_LAUNCHER", str(launcher))
    monkeypatch.delenv("REEFPROOF_REMOTE_ORIGIN", raising=False)
    console = menu.ConsoleController()

    asyncio.run(console._run_desktop("remote-hosted"))

    assert "Remote desktop origin is required" in console.result_text
    assert "PRIVATE_LXC_IP" in console.result_text


def test_control_c_stops_the_desktop_process_group(monkeypatch, tmp_path) -> None:
    class Process:
        returncode = None
        pid = 321

        async def wait(self):
            self.returncode = -15
            return self.returncode

    launcher = tmp_path / "reefproof"
    launcher.write_text("launcher")
    (tmp_path / "package.json").write_text("{}")
    monkeypatch.setenv("REEFPROOF_MENU_LAUNCHER", str(launcher))
    killed = []
    monkeypatch.setattr(menu.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    console = menu.ConsoleController()
    console.view = "foreground-desktop"
    console.desktop_process = cast(asyncio.subprocess.Process, Process())

    asyncio.run(console._stop_desktop())

    assert killed == [(321, menu.signal.SIGTERM)]
    assert console.desktop_process is None
    assert console.view == "main"


def test_desktop_menu_rebuilds_source_even_when_a_packaged_application_exists(
    monkeypatch, tmp_path
) -> None:
    class Process:
        returncode = 0
        pid = 456

        async def communicate(self):
            return b"source desktop started\n", b""

    observed = []

    async def fake_exec(*args, **kwargs):
        observed.append(args)
        return Process()

    launcher = tmp_path / "reefproof"
    launcher.write_text("launcher")
    (tmp_path / "package.json").write_text("{}")
    app = tmp_path / "dist" / "desktop" / "ReefProof-darwin-x64" / "ReefProof.app"
    app.mkdir(parents=True)
    monkeypatch.setenv("REEFPROOF_MENU_LAUNCHER", str(launcher))
    monkeypatch.setattr(menu.asyncio, "create_subprocess_exec", fake_exec)
    console = menu.ConsoleController()

    asyncio.run(console._run_desktop())

    assert observed == [("make", "run/desktop")]
    assert "source desktop started" in console.result_text


def test_desktop_completion_and_control_c_do_not_race(monkeypatch, tmp_path) -> None:
    stopped = asyncio.Event()

    class Process:
        returncode = None
        pid = 654

        async def communicate(self):
            await stopped.wait()
            return b"", b""

        async def wait(self):
            self.returncode = -15
            stopped.set()
            return self.returncode

    async def fake_exec(*args, **kwargs):
        return Process()

    launcher = tmp_path / "reefproof"
    launcher.write_text("launcher")
    (tmp_path / "package.json").write_text("{}")
    monkeypatch.setenv("REEFPROOF_MENU_LAUNCHER", str(launcher))
    monkeypatch.setattr(menu.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(menu.os, "killpg", lambda _pid, _sig: None)

    async def exercise() -> None:
        console = menu.ConsoleController()
        launch = asyncio.create_task(console._run_desktop())
        await asyncio.sleep(0)
        await console._stop_desktop()
        await launch
        assert console.view == "main"
        assert console.desktop_process is None

    asyncio.run(exercise())


def test_numeric_shortcuts_are_derived_from_the_menu_options() -> None:
    console = menu.ConsoleController()

    assert all(
        console._bindings.get_bindings_for_keys((str(index),))
        for index in range(1, len(menu.MAIN_OPTIONS) + 1)
    )


def test_console_arrow_numeric_enter_control_c_and_control_d() -> None:
    console = menu.ConsoleController()
    with (
        create_pipe_input() as pipe_input,
        create_app_session(input=pipe_input, output=DummyOutput()),
    ):
        event = cast(KeyPressEvent, type("Event", (), {"app": console.app})())
        console._bindings.get_bindings_for_keys(("down",))[0].handler(event)
        assert console.selected_index == 1
        manage_choice = next(
            index for index, (key, _) in enumerate(menu.MAIN_OPTIONS, start=1) if key == "manage"
        )
        console._bindings.get_bindings_for_keys((str(manage_choice),))[0].handler(event)
        assert console.view == "serve-choice"
        console.show_results("done")
        console._bindings.get_bindings_for_keys(("c-m",))[0].handler(event)
        assert console.view == "main"
        console.show_palette()
        console._bindings.get_bindings_for_keys(("c-c",))[0].handler(event)
        assert console.view == "main"
        console.show_palette()
        console._bindings.get_bindings_for_keys(("c-d",))[0].handler(event)
        assert console.view == "main"


def test_command_palette_completes_and_parses_help(monkeypatch) -> None:
    catalog = menu._command_catalog()
    completer = menu.GlobCommandCompleter(catalog)
    completions = list(
        completer.get_completions(Document("serv"), CompleteEvent(completion_requested=True))
    )

    assert "serve --no-open" in catalog.candidates
    assert any(
        completion.text == "serve" and completion.display_meta_text for completion in completions
    )
    assert menu.PALETTE_PROMPT == "reefproof> "

    console = menu.ConsoleController()
    console.show_palette()
    initial_matches = console._palette_matches()
    assert any("help" in fragment[1] for fragment in initial_matches)
    assert any("more matches" in fragment[1] for fragment in initial_matches)
    console._page_palette(1)
    assert console._palette_page == "auth"
    assert all(
        completion.text == "auth" or completion.text.startswith("auth ")
        for completion in console._palette_completions()
    )
    console._page_palette(-1)
    assert console._palette_page == "All"
    console._page_palette(1)
    selected: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        console,
        "_begin_interactive_inputs",
        lambda arguments, **kwargs: selected.append(arguments) or True,
    )
    console._run_palette()
    assert selected == [("auth",)]
    console.show_palette()
    console.palette_buffer.set_document(Document("serv", cursor_position=4), bypass_readonly=True)
    assert any("serve --no-open" in fragment[1] for fragment in console._palette_matches())
    console.palette_buffer.set_document(
        Document("auth *session*", cursor_position=len("auth *session*")), bypass_readonly=True
    )
    filtered_matches = console._palette_matches()
    assert any("auth sessions" in fragment[1] for fragment in filtered_matches)
    assert any("auth revoke-session" in fragment[1] for fragment in filtered_matches)
    console._apply_palette_completion()
    assert console.palette_buffer.text in {"auth sessions", "auth revoke-session"}
    console.palette_buffer.set_document(Document("tot", cursor_position=3), bypass_readonly=True)
    assert console._resolve_palette_command("tot") == "auth totp"
    console.palette_buffer.text = "help auth sessions"
    # Exercise the parser/routing seam without scheduling a subprocess.
    console.palette_buffer.text = "snapshot --fixture 'broken"
    console._run_palette()
    assert console.view == "results"
    assert "could not parse command" in console.result_text


def test_highlighted_command_completion_prompts_for_required_params(monkeypatch) -> None:
    console = menu.ConsoleController()
    console.show_palette()
    console.palette_buffer.set_document(
        Document("hydros-check --hydros", cursor_position=len("hydros-check --hydros")),
        bypass_readonly=True,
    )
    console._apply_palette_completion()
    selected = console.palette_buffer.text
    prompted: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        console,
        "_begin_interactive_inputs",
        lambda arguments, **kwargs: prompted.append(arguments) or True,
    )

    console._run_palette()

    assert selected == "hydros-check --hydros-export"
    assert prompted == [("hydros-check", "--hydros-export")]


def test_bounded_results_keep_visible_truncation_notice_and_return_to_main() -> None:
    console = menu.ConsoleController()
    console.show_results("x" * (menu.MAX_VIEW_OUTPUT + 1))

    rendered = "".join(fragment[1] for fragment in console._results_text())
    assert "output truncated in console" in rendered
    console.show_main()
    assert console.view == "main"


def test_palette_results_return_to_a_fresh_repl() -> None:
    console = menu.ConsoleController()
    console.show_results("result", return_view="palette")

    console._return_from_results()

    assert console.view == "palette"
    assert console.palette_buffer.text == ""
    assert console.app.layout.current_control is console.palette_control


def test_palette_prompts_for_missing_required_cli_inputs() -> None:
    console = menu.ConsoleController()

    assert console._missing_inputs(("explain",)) == (menu.MissingInput("invariant_id"),)
    assert console._begin_interactive_inputs(("database", "restore")) is True
    assert console.view == "inputs"
    assert [input_.label for input_ in console.pending_inputs] == ["source", "destination"]
    console.input_buffer.set_document(
        Document("backup.sqlite3", cursor_position=14), bypass_readonly=True
    )
    console._accept_input()
    assert console.pending_arguments == ["database", "restore", "backup.sqlite3"]
    assert console.pending_input_index == 1


def test_palette_prompts_for_explicit_option_without_a_value() -> None:
    console = menu.ConsoleController()

    assert console._missing_inputs(("hydros-check", "--hydros-export"))[0] == (
        menu.MissingInput("--hydros-export", "--hydros-export")
    )
    for arguments in (
        ("snapshot", "--hydros-export"),
        ("snapshot", "--hydros-export="),
    ):
        assert console._missing_inputs(arguments) == (
            menu.MissingInput("--hydros-export", "--hydros-export"),
        )


def test_main_backup_prompts_for_destination_with_development_warning(monkeypatch) -> None:
    monkeypatch.setenv("REEFPROOF_ENVIRONMENT", "development")
    console = menu.ConsoleController()

    console._choose("backup")

    assert console.view == "inputs"
    assert console.pending_arguments == ["database", "backup", "--root"]
    assert [input_.label for input_ in console.pending_inputs] == ["--root"]
    assert ".local" in console.input_notice
    assert "ignored by Git" in console.input_notice
    assert "mounted or otherwise backed-up storage" in console.input_notice


def test_main_backup_omits_development_warning_in_production(monkeypatch) -> None:
    monkeypatch.setenv("REEFPROOF_ENVIRONMENT", "production")
    console = menu.ConsoleController()
    scheduled = []

    def capture(coroutine) -> None:
        scheduled.append(coroutine)
        coroutine.close()

    monkeypatch.setattr(console, "_schedule", capture)

    console._choose("backup")

    assert len(scheduled) == 1


def test_captured_command_combines_stdout_stderr_and_exit_status(monkeypatch) -> None:
    class Process:
        returncode = 17

        async def communicate(self):
            return b"stdout\n", b"stderr\n"

    async def fake_exec(*args, **kwargs):
        return Process()

    monkeypatch.setattr(menu.asyncio, "create_subprocess_exec", fake_exec)
    console = menu.ConsoleController(command_prefix=("reefproof",))
    asyncio.run(console._run_captured(("doctor",)))

    assert "stdout" in console.result_text
    assert "stderr" in console.result_text
    assert "exit status 17" in console.result_text


def test_control_c_during_foreground_spawn_terminates_only_that_child(monkeypatch) -> None:
    class Process:
        stdout = None
        stderr = None
        returncode = None
        terminated = False

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = -15

        async def wait(self) -> int:
            return self.returncode or 0

    process = Process()
    release_spawn = asyncio.Event()

    async def fake_exec(*args, **kwargs):
        await release_spawn.wait()
        return process

    async def exercise() -> None:
        console = menu.ConsoleController(command_prefix=("reefproof",))
        task = asyncio.create_task(console._start_foreground())
        await asyncio.sleep(0)
        await console._stop_foreground()
        release_spawn.set()
        await task
        assert process.terminated is True
        assert console.view == "main"

    monkeypatch.setattr(menu.asyncio, "create_subprocess_exec", fake_exec)
    asyncio.run(exercise())
