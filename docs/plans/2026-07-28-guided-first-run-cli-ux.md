# Guided First-Run CLI UX

Status: In progress.

## Outcome

Make ReefProof discoverable for first-time operators by defaulting to a guided
entry path that starts from ./reefproof with no arguments, while preserving
the read-only safety boundary and existing scripted command behavior.

## Steps

### Phase 1: Lock UX contract and constraints

1. Confirm no-args interactive menu, guided beginner tone, and expert override behavior.
2. Encode safety/auth constraints in UX copy and flow guards.
3. Define onboarding state transitions and failure exits.

### Phase 2: Wrapper discoverability

1. Update reefproof no-args path to route attached terminals into the persistent
   `prompt_toolkit` menu; keep redirected stdin or stdout on non-interactive help.
   The main and serve menus use `prompt_toolkit.shortcuts.choice`: Up/Down moves
   the active item, Enter selects it, Ctrl-C redraws, and Ctrl-D exits. The main
   choices carry distinct emoji and usage-oriented descriptions. Navigation
   wraps between the first and last choices using the current option count.
2. Keep explicit dev/prod handling and improve unsupported-mode remediation text.
3. Add next-command hints after wrapper-level failures.

### Phase 3: Guided onboarding in CLI

1. Add guided onboarding entry in src/reefproof/cli.py, callable from menu and directly.
2. Implement ordered guided steps:
  - Open workbench and show provenance language.
  - Guide TOTP enrollment/reset.
  - Verify evidence storage health.
  - Show next-command cheatsheet.
3. Add beginner default plus expert mode option.

### Phase 4: Error remediation and interactive doctor

1. Standardize one-line failure summary + selectable remediation actions.
2. Add interactive doctor guidance for startup/auth/storage failures.
3. Ensure all suggested fixes remain offline-safe and non-mutating.

### Phase 5: History and completion ergonomics

1. Add dedicated history command in src/reefproof/cli.py.
2. Show recent-commands snippet inside guided flow.
3. Derive the command-palette catalog and descriptions from the live Typer/Click
   registry so interactive documentation cannot drift into a second command map.
4. Complete commands and options while typing, display command/option help as
   completion metadata, and keep contextual instructions in a bottom toolbar.
   Empty-input Tab shows the complete registry. Typed input filters with
   case-insensitive shell globs; plain text is treated as `*text*`.
5. Support `help` and `help <command>` inside the palette, with Tab and Up/Down
   completion selection, history suggestions, shell-aware argument parsing,
   Ctrl-C clearing the current input, and Ctrl-D/`back` returning to the menu.

### Phase 6: Security gating

1. Enforce hard block for rule-edit workflows when TOTP is not enrolled.
2. Keep override policy explicit and off by default.
3. Provide clear unblock instructions in output.

### Phase 7: Tests, docs, rollout

1. Add unit/integration/safety coverage for menu, guided flow, expert mode, and gating.
2. Add negative tests proving no mutation-capable path is introduced.
3. Update quickstart/ops/release docs after behavior lands.
4. Run manual acceptance checklist for onboarding speed and clarity.

## Relevant files

- reefproof: no-args interactive menu and wrapper routing behavior.
- src/reefproof/cli.py: guided command, expert mode, remediation UX, history command, gating UX.
- src/reefproof/auth_totp.py: TOTP state checks used by onboarding/gating.
- src/reefproof/api/sessions.py: session concepts for beginner-safe hints.
- src/reefproof/service/runtime.py: keep serve/runtime behavior stable.
- tests/unit: routing, flags, formatting, history logic tests.
- tests/integration: first-run flow and blocked-rule scenarios.
- tests/safety: structural read-only boundary regressions.
- README.md: quickstart updates post-implementation.
- docs/operations.md: operator behavior notes for guided/expert modes.
- docs/release-criteria.md: release checks updated for onboarding UX.

## Scope and non-goals

### Scope

- Add a no-args arrow-key selection flow and auto-documenting command palette.
- Add a beginner-friendly `reefproof start` command in the Python CLI.
- Add a `reefproof history` command backed by local, append-only command logs.
- Provide concise remediation-oriented guidance for first-run onboarding.

### Non-goals

- No live HYDROS control or mutation behavior.
- No network ingress changes or authority expansion.
- No redesign of existing invariant/storage/auth data models.

## Risks

- Interactive prompts can block in non-interactive contexts if TTY handling is
  incomplete.
- Logging command history must avoid recording secrets and must remain local.
- Guided messaging can drift from runtime behavior without test coverage.
- `prompt_toolkit` is now a runtime and packaging dependency; lockfile and
  packaged-binary verification must cover it.

## Evaluation

- Unit tests for choice routing, registry-derived completion metadata, command
  parsing/help routing, guided behavior, and history.
- PTY checks for Up/Down/Enter selection, completion, Ctrl-C, Ctrl-D, and menu return.
- Manual `./reefproof` acceptance for menu and command-palette discoverability.
- Regression checks for existing CLI command help and exit-code behavior.

## Completion criteria

- `./reefproof` with no arguments offers Up/Down-selectable starter actions.
- The command palette completes registered commands/options and documents the
  current completion without maintaining a parallel command inventory.
- `reefproof start` walks operators through browser, TOTP, and storage steps.
- `reefproof history` shows recent local commands with timestamps.
- Existing scripted command invocations remain compatible.

## Verification

1. Running reefproof with no args and attached stdin/stdout shows the choice menu.
2. Guided onboarding completes with clear success/failure next actions.
3. Expert mode preserves detailed diagnostic output where needed.
4. TOTP-not-enrolled state blocks rule-edit flows with precise remediation.
5. History snippet and dedicated history command both function.
6. Safety tests confirm no new mutation pathways.
7. Existing serve/daemon/storage/auth command semantics remain compatible.
8. The command palette exposes only commands registered by the current CLI and
   sends execution through the normal launcher/history boundary.

## Decisions captured

- No-args opens a persistent `prompt_toolkit` menu only when stdin and stdout
  are TTYs; redirected or piped execution displays help without prompting.
- The launcher resolves development or production before entering the menu.
  Explicit arguments retain `exec` and child exit/signal behavior.
- Completed menu actions return to the starter menu. Foreground `serve` stays
  attached and returns after Ctrl-C; detached serving routes to `daemon start`.
- Prompt Ctrl-C redraws the menu. EOF and Exit end successfully. History stores
  executed commands, not menu navigation.
- Main and serve choices use the library's native choice surface rather than
  numeric text parsing. Main-menu Up/Down navigation wraps over the live option
  sequence without fixed bounds. The command palette uses a persistent `PromptSession`,
  completion metadata, live toolbar help, and history suggestions.
- Completion and documentation are generated from Typer's Click command tree;
  adding a command automatically adds its path, options, and short help.
- Guided output includes exact next commands.
- Hard block on rule edits until TOTP enrollment.
- History UX includes both inline recent snippet and dedicated command.
- History keeps the existing configured data-directory location and tab-separated format.
- Expert mode is a global flag in phase 2.

## Unfinished phases

Guided onboarding refinement, interactive doctor remediation, and rule-edit
security gating remain unfinished and are not implied by the accepted TTY lifecycle.
