"""Full-screen prompt-toolkit console for attached ReefProof launcher sessions."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shlex
import shutil
import signal
import sqlite3
import sys
import time
import webbrowser
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Protocol

import typer
from prompt_toolkit.application import Application
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import CompleteEvent, Completer, Completion, PathCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import HTML, FormattedText
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.containers import DynamicContainer
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.styles import Style
from prompt_toolkit.utils import get_cwidth

from reefproof.service.lifecycle import PidWatcher
from reefproof.settings import load_settings

ChoiceOption = tuple[str, str]
MAX_VIEW_OUTPUT = 16_000

MAIN_OPTIONS: tuple[ChoiceOption, ...] = (
    ("status", "🚀 System status — inspect the safe current state and next action"),
    ("commands", "⌨️ Command palette — discover, autocomplete, and run CLI commands"),
    ("doctor", "🩺 Diagnose setup — inspect SQLite, process, and safety health"),
    ("manage", "📡 Manage workbench — status, start, stop, or restart safely"),
    ("open", "🪸 Open workbench — verify or safely start before opening"),
    ("desktop", "🖥️ Desktop Workbench — choose local-managed or remote-hosted"),
    ("backup", "💾 Back up evidence — copy SQLite safely to backed-up storage"),
    ("exit", "👋 Exit ReefProof — leave without starting a local service"),
)
WORKBENCH_OPTIONS: tuple[ChoiceOption, ...] = (
    ("workbench-status", "Status — inspect endpoint identity, readiness, and ownership"),
    ("workbench-start", "Start detached — start and verify the managed daemon"),
    ("foreground", "Start attached — stream logs; Ctrl-C returns to menu"),
    ("workbench-stop", "Stop — stop only the PID-file-owned daemon"),
    ("workbench-restart", "Restart — restart only the PID-file-owned daemon"),
    ("back", "Back"),
)
DESKTOP_OPTIONS: tuple[ChoiceOption, ...] = (
    ("desktop-local", "Local managed — own one bundled loopback service"),
    ("desktop-remote", "Remote hosted — use the configured private-LAN origin"),
    ("back", "Back"),
)
MAIN_MENU_MESSAGE = "ReefProof • LOCAL ASSURANCE CONSOLE"
SAFETY_HEADER = "observe, model, challenge, alert — never control"
PALETTE_PROMPT = "reefproof> "
DEVELOPMENT_BACKUP_WARNING = (
    "⚠ DEVELOPMENT MODE: ReefProof data under .local is ignored by Git and is not "
    "a backup. Choose a new destination on mounted or otherwise backed-up storage."
)


@dataclass(frozen=True)
class CommandCatalog:
    candidates: tuple[str, ...]
    descriptions: Mapping[str, str]

    def describe(self, text: str) -> str:
        normalized = " ".join(text.strip().split())
        matches = [
            candidate
            for candidate in self.candidates
            if normalized == candidate or normalized.startswith(f"{candidate} ")
        ]
        if not matches:
            if any(text.strip().startswith(f"{candidate} ") for candidate in self.candidates):
                return "Ready to run this command; press Enter."
            return "Type a command; Tab or Up/Down selects a documented completion."
        return self.descriptions[max(matches, key=len)]


@dataclass(frozen=True)
class MissingInput:
    label: str
    option: str | None = None


@dataclass(frozen=True, slots=True)
class MenuSystemStatus:
    environment: str
    daemon_state: str
    daemon_pid: int | None
    owned_apps: tuple[str, ...]
    live_sessions: int | None


class _OwnedProcessState(Protocol):
    @property
    def foreground_process(self) -> object | None: ...

    @property
    def desktop_process(self) -> object | None: ...


def _observe_menu_system_status(controller: _OwnedProcessState) -> MenuSystemStatus:
    environment = os.environ.get("REEFPROOF_ENVIRONMENT", "development").casefold()
    environment_label = {
        "dev": "DEV",
        "development": "DEV",
        "prod": "PROD",
        "production": "PROD",
    }.get(environment, "UNKNOWN")

    daemon_state = "UNKNOWN"
    daemon_pid: int | None = None
    live_sessions: int | None = None
    try:
        settings = load_settings(create_data_directory=False)
        daemon = PidWatcher(settings.data_directory / "reefproof.pid").status()
        daemon_state = daemon.state.value.upper()
        daemon_pid = daemon.pid

        database_path = settings.data_directory / "reefproof.sqlite3"
        if not database_path.exists():
            live_sessions = 0
        else:
            from reefproof.api.sessions import SESSION_MAX_AGE_SECONDS
            from reefproof.storage import Database

            records = Database(database_path).list_active_operator_sessions(
                project_id=settings.project.project_id,
                principal_id=settings.project.acceptance_authority_principal_id,
                authentication_generation=0,
            )
            now = int(time.time())
            live_sessions = sum(
                0 <= now - record.issued_at <= SESSION_MAX_AGE_SECONDS for record in records
            )
    except (OSError, sqlite3.Error, ValueError):
        pass

    owned_apps = ["CONSOLE"]
    if controller.foreground_process is not None:
        owned_apps.append("ATTACHED WORKBENCH")
    if controller.desktop_process is not None:
        owned_apps.append("DESKTOP")
    return MenuSystemStatus(
        environment=environment_label,
        daemon_state=daemon_state,
        daemon_pid=daemon_pid,
        owned_apps=tuple(owned_apps),
        live_sessions=live_sessions,
    )


class GlobCommandCompleter(Completer):
    def __init__(self, catalog: CommandCatalog) -> None:
        self.catalog = catalog
        self.path_completer = PathCompleter(expanduser=True, only_directories=False)

    def get_completions(self, document: Document, complete_event: CompleteEvent):
        text = document.text_before_cursor
        token_start = max(text.rfind(" "), text.rfind("\t")) + 1
        current_token = text[token_start:]
        if "--hydros-export" in text[:token_start]:
            path_document = Document(current_token, cursor_position=len(current_token))
            yield from self.path_completer.get_completions(path_document, complete_event)
            return
        query = text.strip().casefold()
        pattern = query if any(character in query for character in "*?[") else f"*{query}*"
        for candidate in self.catalog.candidates:
            if fnmatchcase(candidate.casefold(), pattern):
                yield Completion(
                    candidate,
                    start_position=-len(document.text_before_cursor),
                    display_meta=self.catalog.descriptions[candidate],
                )


class InputCompleter(Completer):
    """Complete filesystem values for the small set of interactive inputs."""

    def __init__(self, controller: ConsoleController) -> None:
        self.controller = controller
        self.path_completer = PathCompleter(expanduser=True, only_directories=False)
        self.directory_completer = PathCompleter(expanduser=True, only_directories=True)

    def get_completions(self, document: Document, complete_event: CompleteEvent):
        if self._is_hydros_export_input():
            yield from self.path_completer.get_completions(document, complete_event)
        elif self._is_directory_input():
            yield from self.directory_completer.get_completions(document, complete_event)

    def _is_hydros_export_input(self) -> bool:
        if not self.controller.pending_inputs:
            return False
        pending = self.controller.pending_inputs[self.controller.pending_input_index]
        return pending.option == "--hydros-export"

    def _is_directory_input(self) -> bool:
        if not self.controller.pending_inputs:
            return False
        pending = self.controller.pending_inputs[self.controller.pending_input_index]
        return pending.option == "--root"


def _command_prefix() -> tuple[str, ...]:
    launcher = os.environ.get("REEFPROOF_MENU_LAUNCHER")
    if launcher:
        return (launcher,)
    if getattr(sys, "frozen", False):
        return (sys.executable,)
    return (sys.executable, "-m", "reefproof.cli")


def _command_catalog() -> CommandCatalog:
    import reefproof.cli as cli

    descriptions: dict[str, str] = {
        "help": "Show top-level help, or use help <command> for command-specific help.",
        "back": "Return to the starter menu.",
        "exit": "Return to the starter menu.",
    }

    def walk(group: Any, prefix: tuple[str, ...] = ()) -> None:
        for name, command in sorted(getattr(group, "commands", {}).items()):
            if command.hidden or name == "menu":
                continue
            path = (*prefix, name)
            command_text = " ".join(path)
            descriptions[command_text] = command.get_short_help_str()
            for parameter in command.params:
                for option in (
                    *getattr(parameter, "opts", ()),
                    *getattr(parameter, "secondary_opts", ()),
                ):
                    descriptions[f"{command_text} {option}"] = (
                        parameter.help or f"Option for {command_text}."
                    )
            if getattr(command, "commands", None) is not None:
                walk(command, path)

    walk(typer.main.get_command(cli.app))
    return CommandCatalog(tuple(descriptions), descriptions)


def _bounded(text: str) -> str:
    if len(text) <= MAX_VIEW_OUTPUT:
        return text
    return (
        "[output truncated in console; inspect the command log for the complete output]\n"
        + text[-MAX_VIEW_OUTPUT:]
    )


def _fit_terminal_line(text: str, maximum_cells: int) -> str:
    """Keep one rendered line away from the terminal's wrap column."""

    if get_cwidth(text) <= maximum_cells:
        return text
    ellipsis = "…"
    available = max(0, maximum_cells - get_cwidth(ellipsis))
    rendered: list[str] = []
    used = 0
    for character in text:
        width = get_cwidth(character)
        if used + width > available:
            break
        rendered.append(character)
        used += width
    return "".join(rendered).rstrip() + ellipsis


def _menu_option_text(marker: str, index: int, label: str, *, align_icon: bool) -> str:
    prefix = f" {marker} {index}. "
    if not align_icon:
        return prefix + label
    icon, separator, description = label.partition(" ")
    if not separator:
        return prefix + label
    icon_padding = " " * max(0, 2 - get_cwidth(icon))
    return f"{prefix}{icon}{icon_padding} {description}"


class ConsoleController:
    """One application owns all attached-terminal interaction and child output."""

    def __init__(
        self,
        *,
        command_prefix: tuple[str, ...] | None = None,
        system_status_provider: Callable[[ConsoleController], MenuSystemStatus] | None = None,
        terminal_width_provider: Callable[[], int] | None = None,
    ) -> None:
        self.command_prefix = command_prefix or _command_prefix()
        self.catalog = _command_catalog()
        self.view = "main"
        self.options: tuple[ChoiceOption, ...] = MAIN_OPTIONS
        self.selected_index = 0
        self.palette_selected_index = 0
        self.palette_page_index = 0
        self.pending_arguments: list[str] = []
        self.pending_inputs: list[MissingInput] = []
        self.pending_input_index = 0
        self.input_error = ""
        self.input_notice = ""
        self.results_return_view = "main"
        self.result_text = ""
        self.foreground_process: asyncio.subprocess.Process | None = None
        self.desktop_process: asyncio.subprocess.Process | None = None
        self._foreground_stop_requested = False
        self._desktop_stop_requested = False
        self._foreground_tasks: list[asyncio.Task[None]] = []
        self._tasks: set[asyncio.Task[None]] = set()
        self._system_status_provider = system_status_provider or _observe_menu_system_status
        self._terminal_width_provider = terminal_width_provider or (
            lambda: shutil.get_terminal_size(fallback=(80, 24)).columns
        )
        self.system_status = self._system_status_provider(self)
        self.menu_control = FormattedTextControl(self._menu_text, focusable=True)
        self.results_control = FormattedTextControl(self._results_text, focusable=True)
        self.palette_buffer = Buffer(
            completer=GlobCommandCompleter(self.catalog),
            complete_while_typing=False,
            auto_suggest=AutoSuggestFromHistory(),
        )
        self.palette_buffer.on_text_changed += self._reset_palette_selection
        self.palette_control = BufferControl(buffer=self.palette_buffer, focusable=True)
        self.input_buffer = Buffer(
            completer=InputCompleter(self),
            complete_while_typing=False,
        )
        self.input_control = BufferControl(buffer=self.input_buffer, focusable=True)
        self._body = DynamicContainer(self._current_body)
        self._bindings = self._build_bindings()
        root = HSplit(
            [
                Window(
                    FormattedTextControl(HTML("<b>ReefProof</b>  LOCAL ASSURANCE CONSOLE")),
                    height=1,
                    style="class:header",
                ),
                self._body,
                Window(FormattedTextControl(self._footer_text), height=1, style="class:footer"),
            ]
        )
        self.app: Application[int] = Application(
            layout=Layout(root, focused_element=self.menu_control),
            key_bindings=self._bindings,
            full_screen=True,
            style=Style.from_dict(
                {
                    "header": "bg:#005f87 #ffffff",
                    "footer": "bg:#303030 #ffffff",
                    "selected": "bg:#005f87 #ffffff bold",
                    "title": "bold",
                    "failure": "#ff5f5f",
                    "system-status": "#00d7ff bold",
                }
            ),
            color_depth=ColorDepth.ANSI_COLORS_ONLY,
            mouse_support=False,
        )
        self._focus(self.menu_control)

    def _focus(self, control: Any) -> None:
        self.app.layout.focus(control)

    def _menu_text(self) -> FormattedText:
        maximum_cells = max(19, self._terminal_width_provider() - 1)
        if self.view == "serve-choice":
            lines: list[tuple[str, str]] = [
                (
                    "class:title",
                    _fit_terminal_line("Manage local workbench", maximum_cells) + "\n\n",
                )
            ]
        elif self.view == "desktop-choice":
            lines = [
                (
                    "class:title",
                    _fit_terminal_line("Choose desktop authority", maximum_cells) + "\n",
                ),
                (
                    "",
                    _fit_terminal_line(
                        "Remote mode never starts or uses a local ReefProof runtime.",
                        maximum_cells,
                    )
                    + "\n\n",
                ),
            ]
        else:
            lines = [
                (
                    "class:title",
                    _fit_terminal_line("Choose a safe, read-only operator workflow.", maximum_cells)
                    + "\n",
                ),
                (
                    "",
                    _fit_terminal_line(f"{SAFETY_HEADER.capitalize()}.", maximum_cells) + "\n",
                ),
            ]
            lines.extend(
                ("class:system-status", line + "\n")
                for line in self._system_status_lines(maximum_cells)
            )
            lines.append(("", "\n"))
        for index, (_, label) in enumerate(self.options, start=1):
            style = "class:selected" if index - 1 == self.selected_index else ""
            marker = ">" if index - 1 == self.selected_index else " "
            option = _menu_option_text(marker, index, label, align_icon=self.view == "main")
            line = _fit_terminal_line(option, maximum_cells)
            lines.append((style, line + "\n"))
        return FormattedText(lines)

    def _system_status_lines(self, maximum_cells: int) -> tuple[str, ...]:
        status = self.system_status
        pid = f" (PID {status.daemon_pid})" if status.daemon_pid is not None else ""
        sessions = "UNKNOWN" if status.live_sessions is None else str(status.live_sessions)
        system = f"System: {status.environment} • daemon {status.daemon_state}{pid}"
        owned = f"Owned: apps {' + '.join(status.owned_apps)} • sessions {sessions} LIVE"
        combined = f"{system} • {owned.removeprefix('Owned: ')}"
        if get_cwidth(combined) <= maximum_cells:
            return (combined,)
        return (
            _fit_terminal_line(system, maximum_cells),
            _fit_terminal_line(owned, maximum_cells),
        )

    def _results_text(self) -> FormattedText:
        return FormattedText(
            [("class:title", "Command result\n\n"), ("", _bounded(self.result_text))]
        )

    def _current_body(self):
        if self.view in {"main", "serve-choice", "desktop-choice"}:
            return Window(self.menu_control, always_hide_cursor=True)
        if self.view in {"results", "foreground-serving", "foreground-desktop"}:
            return Window(self.results_control, wrap_lines=True, always_hide_cursor=True)
        if self.view == "inputs":
            return HSplit(
                [
                    Window(
                        FormattedTextControl(self._input_prompt),
                        height=2 if self.input_notice else 1,
                    ),
                    VSplit(
                        [
                            Window(FormattedTextControl("input> "), width=7),
                            Window(self.input_control, height=1),
                        ],
                        height=1,
                    ),
                ]
            )
        return HSplit(
            [
                Window(
                    FormattedTextControl(self._palette_title),
                    height=1,
                ),
                VSplit(
                    [
                        Window(FormattedTextControl(PALETTE_PROMPT), width=len(PALETTE_PROMPT)),
                        Window(self.palette_control, height=1),
                    ],
                    height=1,
                ),
                Window(FormattedTextControl(self._palette_hint), height=1),
                Window(FormattedTextControl(self._palette_matches), wrap_lines=True),
            ]
        )

    def _palette_hint(self):
        return self.catalog.describe(self.palette_buffer.text)

    def _input_prompt(self):
        pending = self.pending_inputs[self.pending_input_index]
        prompt = (
            f"Required input {self.pending_input_index + 1}/{len(self.pending_inputs)}: "
            f"{pending.label}"
        )
        if self.input_error:
            prompt += f" — {self.input_error}"
        if self.input_notice:
            prompt = f"{self.input_notice}\n{prompt}"
        return HTML(f"<b>{prompt}</b>")

    @property
    def _palette_pages(self) -> tuple[str, ...]:
        top_level = sorted(
            candidate
            for candidate in self.catalog.candidates
            if " " not in candidate and candidate not in {"help", "back", "exit"}
        )
        return ("All", *top_level)

    @property
    def _palette_page(self) -> str:
        return self._palette_pages[self.palette_page_index]

    def _palette_title(self):
        page = "all commands" if self._palette_page == "All" else f"{self._palette_page} commands"
        return HTML(f"<b>Command palette</b>  {page}; commands come from the live CLI registry.")

    def _palette_completions(self, query: str | None = None) -> tuple[Completion, ...]:
        completer = self.palette_buffer.completer
        if completer is None:
            return ()
        document = (
            self.palette_buffer.document
            if query is None
            else Document(query, cursor_position=len(query))
        )
        completions = tuple(
            completer.get_completions(
                document,
                CompleteEvent(completion_requested=True),
            )
        )
        if self._palette_page == "All":
            return completions
        return tuple(
            completion
            for completion in completions
            if completion.text == self._palette_page
            or completion.text.startswith(f"{self._palette_page} ")
        )

    def _palette_matches(self) -> FormattedText:
        completions = self._palette_completions()
        if not completions:
            command_line = self.palette_buffer.text.strip()
            if any(
                command_line.startswith(f"{candidate} ") for candidate in self.catalog.candidates
            ):
                return FormattedText([("", "\nCommand arguments accepted; press Enter to run.\n")])
            return FormattedText([("class:failure", "\nNo matching registered command.")])
        visible = completions[:8]
        lines: list[tuple[str, str]] = [("", "\n")]
        for index, completion in enumerate(visible):
            style = "class:selected" if index == self.palette_selected_index else ""
            marker = ">" if index == self.palette_selected_index else " "
            lines.append((style, f" {marker} {completion.text}  {completion.display_meta_text}\n"))
        if len(completions) > len(visible):
            lines.append(("", f"   … {len(completions) - len(visible)} more matches\n"))
        return FormattedText(lines)

    def _reset_palette_selection(self, _: Buffer) -> None:
        self.palette_selected_index = 0
        if hasattr(self, "app"):
            self.app.invalidate()

    def _footer_text(self):
        if self.view == "palette":
            message = (
                f"←/→ page: {self._palette_page} • Tab/Up/Down complete • "
                "Enter run • Ctrl-C or Ctrl-D back"
            )
        elif self.view == "inputs":
            message = "Tab complete path • Enter accept input • Ctrl-C or Ctrl-D cancel to REPL"
        elif self.view == "results":
            destination = "REPL" if self.results_return_view == "palette" else "main"
            message = f"Enter return to {destination} • Ctrl-C return to {destination}"
        elif self.view == "foreground-serving":
            message = "Ctrl-C stop this local serve process and return to main"
        elif self.view == "foreground-desktop":
            message = "Ctrl-C stop the desktop app and any runtime it owns, then return to main"
        else:
            message = "Up/Down select • number choose • Enter confirm • Ctrl-C redraw • Ctrl-D exit"
        maximum_cells = max(19, self._terminal_width_provider() - 1)
        return _fit_terminal_line(message, maximum_cells)

    def _build_bindings(self) -> KeyBindings:
        bindings = KeyBindings()

        @bindings.add("up", eager=True)
        def up(event: KeyPressEvent) -> None:
            if self.view == "palette":
                self._select_palette_completion(-1)
                return
            if self.view in {"main", "serve-choice", "desktop-choice"}:
                self.selected_index = (self.selected_index - 1) % len(self.options)
                event.app.invalidate()

        @bindings.add("down", eager=True)
        def down(event: KeyPressEvent) -> None:
            if self.view == "palette":
                self._select_palette_completion(1)
                return
            if self.view in {"main", "serve-choice", "desktop-choice"}:
                self.selected_index = (self.selected_index + 1) % len(self.options)
                event.app.invalidate()

        @bindings.add("left", eager=True)
        def previous_page(event: KeyPressEvent) -> None:
            if self.view == "palette":
                self._page_palette(-1)

        @bindings.add("right", eager=True)
        def next_page(event: KeyPressEvent) -> None:
            if self.view == "palette":
                self._page_palette(1)

        @bindings.add("enter", eager=True)
        def enter(event: KeyPressEvent) -> None:
            if self.view in {"main", "serve-choice", "desktop-choice"}:
                self._choose(self.options[self.selected_index][0])
            elif self.view == "results":
                self._return_from_results()
            elif self.view == "palette":
                self._run_palette()
            elif self.view == "inputs":
                self._accept_input()

        @bindings.add("tab", filter=Condition(lambda: self.view == "palette"), eager=True)
        def tab(event: KeyPressEvent) -> None:
            self._apply_palette_completion()

        @bindings.add("tab", filter=Condition(lambda: self.view == "inputs"), eager=True)
        def complete_input(event: KeyPressEvent) -> None:
            completer = self.input_buffer.completer
            if completer is None:
                return
            completions = tuple(
                completer.get_completions(
                    self.input_buffer.document,
                    CompleteEvent(completion_requested=True),
                )
            )
            if completions:
                completion = completions[0]
                self.input_buffer.apply_completion(completion)

        @bindings.add("c-c", eager=True)
        def cancel(event: KeyPressEvent) -> None:
            if self.view == "foreground-serving":
                self._schedule(self._stop_foreground())
            elif self.view == "foreground-desktop":
                self._schedule(self._stop_desktop())
            elif self.view == "results":
                self._return_from_results()
            elif self.view == "inputs":
                self.show_palette()
            else:
                self.show_main()

        @bindings.add("c-d", eager=True)
        def eof(event: KeyPressEvent) -> None:
            if self.view == "main":
                event.app.exit(result=0)
            elif self.view == "inputs":
                self.show_palette()
            else:
                self.show_main()

        menu_shortcut_count = max(len(MAIN_OPTIONS), len(WORKBENCH_OPTIONS), len(DESKTOP_OPTIONS))
        for number in range(1, menu_shortcut_count + 1):

            @bindings.add(
                str(number),
                filter=Condition(lambda: self.view in {"main", "serve-choice", "desktop-choice"}),
                eager=True,
            )
            def numeric(event: KeyPressEvent, choice: int = number) -> None:
                if choice <= len(self.options):
                    self.selected_index = choice - 1
                    self._choose(self.options[self.selected_index][0])

        return bindings

    def _select_palette_completion(self, direction: int) -> None:
        completions = self._palette_completions()
        if completions:
            self.palette_selected_index = (self.palette_selected_index + direction) % len(
                completions
            )
            self.app.invalidate()

    def _page_palette(self, direction: int) -> None:
        self.palette_page_index = (self.palette_page_index + direction) % len(self._palette_pages)
        self.palette_selected_index = 0
        self.app.invalidate()

    def _apply_palette_completion(self) -> None:
        completions = self._palette_completions()
        if completions:
            self.palette_buffer.text = completions[self.palette_selected_index].text
            self.palette_buffer.cursor_position = len(self.palette_buffer.text)

    def _resolve_palette_command(self, command_line: str) -> str:
        """Resolve a palette search to its highlighted full CLI command."""
        if command_line in self.catalog.candidates or command_line.startswith("help "):
            return command_line
        completions = self._palette_completions(command_line)
        if completions:
            return completions[self.palette_selected_index].text
        return command_line

    def _missing_inputs(self, arguments: tuple[str, ...]) -> tuple[MissingInput, ...]:
        """Find required Click parameters that were not supplied in the REPL argv."""
        import reefproof.cli as cli

        command: Any = typer.main.get_command(cli.app)
        consumed = 0
        for token in arguments:
            child = getattr(command, "commands", {}).get(token)
            if child is None:
                break
            command = child
            consumed += 1
        remaining = arguments[consumed:]
        positional_values = [value for value in remaining if not value.startswith("-")]
        positional_index = 0
        missing: list[MissingInput] = []
        for parameter in command.params:
            options = tuple(
                option for option in getattr(parameter, "opts", ()) if option.startswith("-")
            )
            if options:
                if not getattr(parameter, "is_flag", False):
                    dangling = any(
                        (
                            value == option
                            and (
                                index + 1 >= len(remaining) or remaining[index + 1].startswith("-")
                            )
                        )
                        or value == f"{option}="
                        for index, value in enumerate(remaining)
                        for option in options
                    )
                    if dangling:
                        preferred = next(
                            (option for option in options if option.startswith("--")), options[0]
                        )
                        missing.append(MissingInput(preferred, preferred))
                        continue
                if not parameter.required:
                    continue
                supplied = False
                for index, value in enumerate(remaining):
                    for option in options:
                        if value.startswith(f"{option}="):
                            supplied = bool(value.split("=", 1)[1])
                        elif value == option:
                            supplied = index + 1 < len(remaining) and not remaining[
                                index + 1
                            ].startswith("-")
                        if supplied:
                            break
                    if supplied:
                        break
                if not supplied:
                    preferred = next(
                        (option for option in options if option.startswith("--")), options[0]
                    )
                    missing.append(MissingInput(preferred, preferred))
            elif parameter.required and positional_index >= len(positional_values):
                missing.append(MissingInput(parameter.human_readable_name))
            elif positional_index < len(positional_values):
                positional_index += 1
        return tuple(missing)

    def _begin_interactive_inputs(self, arguments: tuple[str, ...], *, notice: str = "") -> bool:
        missing = self._missing_inputs(arguments)
        if not missing:
            return False
        self.pending_arguments = list(arguments)
        self.pending_inputs = list(missing)
        self.pending_input_index = 0
        self.input_error = ""
        self.input_notice = notice
        self.input_buffer.reset()
        self.view = "inputs"
        self._focus(self.input_control)
        self.app.invalidate()
        return True

    def _accept_input(self) -> None:
        value = self.input_buffer.text.strip()
        if not value:
            self.input_error = "Input is required."
            self.app.invalidate()
            return
        pending = self.pending_inputs[self.pending_input_index]
        if pending.option is not None:
            self.pending_arguments.extend((pending.option, value))
        else:
            self.pending_arguments.append(value)
        self.pending_input_index += 1
        self.input_error = ""
        if self.pending_input_index < len(self.pending_inputs):
            self.input_buffer.reset()
            self.app.invalidate()
            return
        arguments = tuple(self.pending_arguments)
        self.show_results(
            f"$ reefproof {' '.join(arguments)}\n\nRunning…",
            return_view="palette",
        )
        self._schedule(self._run_captured(arguments, return_view="palette"))

    def show_main(self) -> None:
        self.view, self.options, self.selected_index = "main", MAIN_OPTIONS, 0
        self.system_status = self._system_status_provider(self)
        self._focus(self.menu_control)
        self.app.invalidate()

    @staticmethod
    def _development_backup_warning() -> str:
        environment = os.environ.get("REEFPROOF_ENVIRONMENT", "development").casefold()
        if environment in {"dev", "development"}:
            return DEVELOPMENT_BACKUP_WARNING
        return ""

    def _schedule(self, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def show_results(self, text: str, *, return_view: str = "main") -> None:
        self.view, self.result_text, self.results_return_view = "results", text, return_view
        self._focus(self.results_control)
        self.app.invalidate()

    def _return_from_results(self) -> None:
        if self.results_return_view == "palette":
            self.show_palette()
        elif self.results_return_view == "workbench":
            self.show_workbench_choice()
        else:
            self.show_main()

    def show_palette(self) -> None:
        self.view = "palette"
        self.palette_buffer.reset()
        self.palette_selected_index = 0
        self.palette_page_index = 0
        self._focus(self.palette_control)
        self.app.invalidate()

    def show_workbench_choice(self) -> None:
        self.view, self.options, self.selected_index = "serve-choice", WORKBENCH_OPTIONS, 0
        self._focus(self.menu_control)
        self.app.invalidate()

    def show_desktop_choice(self) -> None:
        self.view, self.options, self.selected_index = "desktop-choice", DESKTOP_OPTIONS, 0
        self._focus(self.menu_control)
        self.app.invalidate()

    def _choose(self, choice: str) -> None:
        if self.view == "main":
            if choice == "exit":
                self.app.exit(result=0)
            elif choice == "commands":
                self.show_palette()
            elif choice == "manage":
                self.show_workbench_choice()
            elif choice == "open":
                self._schedule(self._open_workbench())
            elif choice == "desktop":
                self.show_desktop_choice()
            elif choice == "backup":
                import reefproof.cli as cli

                settings = cli.load_settings()
                if (
                    settings.storage.backup_directory is not None
                    or os.environ.get("REEFPROOF_ENVIRONMENT", "development").casefold()
                    == "production"
                ):
                    self._schedule(self._run_captured(("database", "backup")))
                else:
                    self._begin_interactive_inputs(
                        ("database", "backup", "--root"),
                        notice=self._development_backup_warning(),
                    )
            else:
                arguments = {
                    "status": ("status",),
                    "doctor": ("doctor",),
                }[choice]
                self._schedule(self._run_captured(arguments))
        elif choice == "back":
            self.show_main()
        elif choice == "desktop-local":
            self._schedule(self._run_desktop("local-managed"))
        elif choice == "desktop-remote":
            self._schedule(self._run_desktop("remote-hosted"))
        elif choice == "workbench-status":
            self._schedule(self._run_captured(("status",), return_view="workbench"))
        elif choice == "workbench-start":
            self._schedule(self._run_captured(("daemon", "start"), return_view="workbench"))
        elif choice == "workbench-stop":
            self._schedule(self._run_captured(("daemon", "stop"), return_view="workbench"))
        elif choice == "workbench-restart":
            self._schedule(self._run_captured(("daemon", "restart"), return_view="workbench"))
        elif choice == "foreground":
            self._schedule(self._start_foreground())

    async def _open_workbench(self) -> None:
        import reefproof.cli as cli
        from reefproof.service.workbench import EndpointState, observe_workbench

        settings = cli.load_settings()
        lifecycle = cli._daemon_lifecycle(pid_file=None)
        observation = await asyncio.to_thread(observe_workbench, settings, lifecycle)
        if observation.endpoint is EndpointState.FOREIGN:
            self.show_results(
                "FAIL: configured interface is occupied by a non-ReefProof listener.\n"
                "No process was changed. Use Manage workbench → Status."
            )
            return
        if observation.endpoint is EndpointState.STOPPED:
            process = await asyncio.create_subprocess_exec(
                *self.command_prefix,
                "daemon",
                "start",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                self.show_results(
                    "$ reefproof daemon start\n\n"
                    + stdout.decode(errors="replace")
                    + stderr.decode(errors="replace")
                    + f"\n[exit status {process.returncode}]\n"
                )
                return
            observation = await asyncio.to_thread(observe_workbench, settings, lifecycle)
        if observation.endpoint is not EndpointState.REEFPROOF:
            self.show_results("FAIL: ReefProof did not become reachable; browser was not opened.")
            return
        opened = await asyncio.to_thread(webbrowser.open, observation.workbench_url)
        detail = "Opened the verified local Workbench." if opened else "Browser did not open."
        self.show_results(f"{detail}\n{observation.workbench_url}")

    async def _run_desktop(self, mode: str = "local-managed") -> None:
        launcher = os.environ.get("REEFPROOF_MENU_LAUNCHER")
        repository_root = Path(launcher).resolve().parent if launcher else Path.cwd()
        if not (repository_root / "package.json").is_file():
            self.show_results(
                "Desktop launch is available from a ReefProof source checkout.\n"
                "Use make run/desktop there."
            )
            return

        child_environment = dict(os.environ)
        child_environment["REEFPROOF_DESKTOP_MODE"] = mode
        if mode == "remote-hosted" and not child_environment.get("REEFPROOF_REMOTE_ORIGIN"):
            self.show_results(
                "Remote desktop origin is required. Restart this console with:\n\n"
                "REEFPROOF_REMOTE_ORIGIN=http://PRIVATE_LXC_IP:8787 ./reefproof\n\n"
                "Then choose Desktop Workbench → Remote hosted."
            )
            return
        if mode == "local-managed":
            child_environment.pop("REEFPROOF_REMOTE_ORIGIN", None)

        self._desktop_stop_requested = False
        self.view = "foreground-desktop"
        make_target = "run/desktop"
        self.result_text = f"$ make {make_target}\n\nLaunching ReefProof desktop in {mode} mode…"
        self._focus(self.results_control)
        self.app.invalidate()
        self.desktop_process = await asyncio.create_subprocess_exec(
            "make",
            make_target,
            cwd=repository_root,
            env=child_environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        if self._desktop_stop_requested:
            await self._terminate_desktop_process()
            self.show_main()
            return
        process = self.desktop_process
        stdout, stderr = await process.communicate()
        output = stdout.decode(errors="replace") + stderr.decode(errors="replace")
        returncode = process.returncode
        if self.desktop_process is process:
            self.desktop_process = None
        if self.view == "foreground-desktop":
            self.show_results(
                f"$ make {make_target}\n\nMode: {mode}\n{output}\n[exit status {returncode}]\n"
            )

    async def _terminate_desktop_process(self) -> None:
        process = self.desktop_process
        if process is not None and process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            await process.wait()
        self.desktop_process = None

    async def _stop_desktop(self) -> None:
        self._desktop_stop_requested = True
        await self._terminate_desktop_process()
        self.show_main()

    async def _run_captured(self, arguments: tuple[str, ...], *, return_view: str = "main") -> None:
        self.show_results(f"$ reefproof {' '.join(arguments)}\n\nRunning…", return_view=return_view)
        process = await asyncio.create_subprocess_exec(
            *self.command_prefix,
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        output = stdout.decode(errors="replace") + stderr.decode(errors="replace")
        outcome = f"\n[exit status {process.returncode}]\n"
        self.show_results(
            f"$ reefproof {' '.join(arguments)}\n\n{output}{outcome}",
            return_view=return_view,
        )

    def _run_palette(self) -> None:
        command_line = self.palette_buffer.text.strip()
        if not command_line:
            completions = self._palette_completions()
            if not completions:
                return
            command_line = completions[self.palette_selected_index].text
        command_line = self._resolve_palette_command(command_line)
        try:
            arguments = tuple(shlex.split(command_line))
        except ValueError as error:
            self.show_results(f"FAIL: could not parse command — {error}", return_view="palette")
            return
        if arguments[0] in {"back", "exit"}:
            self.show_main()
            return
        if arguments[0] == "help":
            arguments = (*arguments[1:], "--help") if len(arguments) > 1 else ("--help",)
        if self._begin_interactive_inputs(arguments):
            return
        self._schedule(self._run_captured(arguments, return_view="palette"))

    async def _start_foreground(self) -> None:
        self._foreground_stop_requested = False
        self.view = "foreground-serving"
        self.result_text = "$ reefproof serve --no-open\n\nStarting local workbench at http://127.0.0.1:8787/workbench\n"
        self._focus(self.results_control)
        self.app.invalidate()
        self.foreground_process = await asyncio.create_subprocess_exec(
            *self.command_prefix,
            "serve",
            "--no-open",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if self._foreground_stop_requested:
            self.foreground_process.terminate()
            await self.foreground_process.wait()
            self.foreground_process = None
            self.show_main()
            return
        self._foreground_tasks = [
            asyncio.create_task(self._stream(channel))
            for channel in (self.foreground_process.stdout, self.foreground_process.stderr)
            if channel is not None
        ]
        await self.foreground_process.wait()
        await asyncio.gather(*self._foreground_tasks, return_exceptions=True)
        returncode = self.foreground_process.returncode
        self.foreground_process = None
        if self.view == "foreground-serving":
            self.result_text += f"\n[serve exited with status {returncode}]"
            self.show_results(self.result_text)

    async def _stream(self, channel: asyncio.StreamReader) -> None:
        while line := await channel.readline():
            self.result_text = _bounded(self.result_text + line.decode(errors="replace"))
            self.app.invalidate()

    async def _stop_foreground(self) -> None:
        self._foreground_stop_requested = True
        process = self.foreground_process
        if process is not None and process.returncode is None:
            process.terminate()
            await process.wait()
        self.foreground_process = None
        self.show_main()

    async def run_async(self) -> int:
        return await self.app.run_async()


def run_menu() -> int:
    """Run the one full-screen attached-terminal console."""
    return asyncio.run(ConsoleController().run_async())
