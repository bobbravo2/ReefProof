# Current State

Last updated: 2026-08-01

## Current product gate

The first real offline HYDROS semantic finding is accepted. Customer 0 confirmed from
the HYDROS Option screen that the observed raw value `"1"` at
`$.Option["Option"].tempFmt` means Fahrenheit and that Fahrenheit is expected.
`hydros-check` normalizes only that property, persists the snapshot and an
`RP-UNIT-001` PASS evaluation, and leaves all other vendor semantics unknown.

The accepted v0.1 gate is now the first complete electrical-assurance slice
from that private export. The source contains no heater, so no heater assurance
is claimed. The generated snapshot is observed evidence, not an annotated
digital twin. ReefProof must first prevent secret-bearing Tuya fields from
escaping the protected raw-evidence store, then resolve represented physical
ports, overlay separately authored electrical intent, and explain and persist
one deterministic operator verification. The initial evidence-backed result is
HIGH-CONCERN `UNKNOWN`: tiered load-shedding modes exist, but automatic
activation is not proven. The detailed sequence is in
`docs/plans/2026-08-01-electrical-assurance-ux-and-architecture.md`.

## Benchmark harness

`scripts/1-shot-eval-benchmark.sh` now resolves the repo root from its own
location, reads the tracked prompt file
`scripts/1-shot-eval-benchmark.prompt.txt`, and writes run artifacts beneath
`.local/1-shot-results/reefproof-startup-benchmark-<timestamp>/`.
`Makefile` now exposes the operator entry point as `make benchmark` and keeps
`make 1-shot-eval-benchmark` as a backward-compatible alias.
The captured top-level contract matches the grounded directory shape from
`/private/tmp/reefproof-startup-benchmark-20260726-132744`.
Shell syntax and local artifact layout were verified here; a live Codex replay
still needs network access to finish successfully in this sandbox.

## Local build handoff

`make build/binary` now prints copy-pasteable `version`, `doctor`, and `demo`
commands for `dist/reefproof` after verification. `make build/container` prints
the equivalent read-only OCI commands, using the revision-derived image tag
and the automatically detected Podman-or-Docker runtime. Browser and CLI
acceptance testing is pending.

The repository-root executable `./reefproof` is the main local CLI launcher.
`REEFPROOF_ENV=dev` selects source execution through `uv`; `REEFPROOF_ENV=prod`
selects the verified `dist/reefproof` artifact and fails if it is absent.
With attached stdin and stdout, no-argument execution enters a persistent
`prompt_toolkit` starter menu with Up/Down selection and a registry-derived,
auto-documenting command palette; redirected execution remains non-interactive.
Interactive buffers now use filter-compatible completion configuration, so
typing at required-input prompts no longer crashes the event loop.
The top-level backup workflow delegates to `storage backup`; development mode
warns that Git-ignored `.local` data is not itself protected and asks for a
destination on mounted or independently backed-up storage. Explicit arguments
retain child exit behavior.

## Explicit container serving

Commit `34efd38` adds explicit `serve --bind` and `--port` overrides while
preserving the default loopback bind and the OCI `version` default. Podman
acceptance is `VERIFIED` for image `reefproof:build-34efd387d70d`: detached
serve, `0.0.0.0` bind, host-loopback `/health/live` and `/workbench`, mounted
SQLite persistence, backup, restore into a new volume, and clean stop. The
initial `/health/ready` response is honestly `503 unready` until configuration
has been evaluated. Backup/restore documentation now discloses named-volume
data-loss risk and keeps the data volume writable for SQLite WAL/locks.

Acceptance found that the prior macOS PyInstaller artifact failed at startup
with `ModuleNotFoundError: _scproxy` while importing httpx through the Home
Assistant adapter. `scripts/build-binary.sh` now adds `_scproxy` as a Darwin
hidden import. A clean committed-tree macOS rebuild passed binary verification;
production `version`, daemon start, and daemon stop acceptance also passed.

## Stable assurance kernel

- Offline authored fixtures normalize deterministically into canonical
  snapshots and typed reliability graphs.
- Fifteen registered three-state invariants preserve `PASS`, `FAIL`, and
  `UNKNOWN` with explanations and evidence.
- SQLite WAL persistence stores snapshots, evaluations, finding transitions,
  alert attempts, immutable authored rule revisions, project authority chains,
  and schema-versioned migrations.
- The local source CLI and loopback workbench exercise offline assurance without
  live HYDROS access, MQTT publication, controller mutation, or remediation.

## Runtime and persistence reality

The source runtime targets CPython 3.13. SQLite schema revision 6 includes the
preserved trust-event stream. TOTP material lives in an ignored mode-0600 file
outside SQLite and backups. No live device credentials or private HYDROS
capture are tracked.

## Desktop presentation shell

The repository now has a minimal Electron main process that owns an existing
loopback Workbench server on desktop-only port 8790 and renders `/workbench`
without a second renderer. Node integration is disabled, context isolation and
sandboxing are enabled, permissions default-deny, navigation stays on the owned
origin, and all child windows are denied. No preload or IPC bridge exists.
The focused deterministic suite and a native Electron launch reached the
Workbench and loaded its existing static assets. macOS screen capture was
denied, so screenshot evidence is `NOT TESTED`.

The macOS-first packaging path reads version `0.1.0` from `pyproject.toml`,
generates a native ICNS, stages only the compiled Electron main process, and
embeds the verified ReefProof executable as an application resource. The
unsigned x64 `.app` structure, plist versions, ASAR, executable resources, and
icon digest are `VERIFIED` by `npm run desktop:package`. The locally inspected
bundle build now creates the embedded CLI from current committed `HEAD` in a
temporary detached worktree and verifies its version and Git revision; stale
checkout `dist/reefproof` artifacts are not used. Signing, notarization,
DMG/installers, universal Apple Silicon, and
non-macOS packages remain `NOT TESTED` or unimplemented.
The pull-request/main delivery workflow builds and uploads an unsigned macOS
`.app` ZIP after its quality gate. Hosted runner execution remains `NOT TESTED`,
and the tag-triggered release workflow does not publish the desktop artifact.
Repository-owned local `act` tasks prefer `podman-machine-default`, start that
existing machine when stopped, and fall back to a running Docker daemon only
when the Podman machine is unavailable. The baseline now permits accepted
offline HYDROS evidence while structurally rejecting MQTT-named runtime modules
and vendor transport-client imports.

## Release-candidate status

There is no v0.1 release candidate. The preservation branch commits legitimate
WIP for review; commit existence does not add a subsystem to release scope.
Nothing has been pushed, tagged, published, deployed, or accepted on the
Outie/sentient target.

## Deferred implemented subsystems

Identity-bound/TOTP trust controls, the read-only SQLite explorer, daemon
lifecycle, development reloader, Home Assistant delivery, the rich multipage
workbench/aquarium layer, project interview/candidate/replay workflows, agent
usage/cost telemetry, and generalized agent/physical-proposal workflows are
preserved but excluded from the current proof-of-trust gate.

## Verification

Known focused baseline: `./scripts/check-baseline.sh` passed on 2026-07-26.
The local API/OpenAPI refinement is `VERIFIED`: OpenAPI now declares bearer
token and signed session-cookie schemes, groups operations by boundary, and
the browser contract exports only `/v1/*` API routes (not the HTML workbench
page). `make check` passed after the change, including contract parity,
TypeScript, browser tests, and the full Python suite. No commit or publication
was made.

Grounding startup extraction is `VERIFIED` in this sandbox after updating
`.codex/skills/reefproof-project-grounding/scripts/extract.py` to run Git
subprocesses with a neutral global config fallback. Extractor outputs currently
measure about 2.6 KB JSON (~650 tokens) and 2.2 KB text (~540 tokens), with
local repeated-run means near 147 ms (json) and 159 ms (text).

Workbench session-gating acceptance is `VERIFIED`: browser pages now block
behind startup authentication, an explicit nav logout control calls
`/v1/workbench/session/logout`, and frontend session invalidation re-gates the
UI when protected API calls return `401` or when the periodic session probe
detects a missing/expired cookie. Focused frontend validation passed via
`npm run build` and `node --test tests/web/workbench.test.cjs`.

The attached no-argument launcher now uses one full-screen ANSI-only
`prompt_toolkit` application for its main menu, results, command palette, and
serve choices. It captures short-command output, streams only the foreground
local `serve --no-open` child into the console, and returns to the main view
after non-destructive actions. Focused controller and isolated PTY coverage
verify numeric/arrow routes, captured failure recovery, detached serving,
clean exit, and explicit-argv/non-TTY launcher preservation. Guided onboarding,
interactive doctor remediation, and rule-edit gating remain unfinished.

## Material unknowns

An operator-supplied HYDROS Chrome Device Settings Download Config export was
normalized offline from preserved raw bytes. The importer produces 30 observed
entities with raw source paths and currently copies unmodeled records into
normalized vendor extensions. Because the export includes secret-like Tuya and
network-identifying fields, that behavior is a v0.1 release blocker. Exported
field semantics, physical-port relationships, circuit/protection/backup-power
mappings, and the meaning of `lowPower` and `maxOnTime: 0` remain `UNKNOWN`.
The export has no heater; heater rules remain authored fixture coverage only.
Live HYDROS and Home Assistant behavior, hosted release automation, public
artifact publication, target-LXC acceptance, and the broader public support
matrix are `NOT TESTED` or blocked by decisions in `docs/roadmap.md`.
