# Electron desktop shell

## Outcome

Add a minimal native Electron shell that presents the existing loopback
Workbench without copying renderer or domain logic.

## Scope and non-goals

- Add one Electron main process, conservative navigation policy, and owned
  development-server lifecycle.
- Expose native status/build metadata, offline diagnostics, owned-server
  restart, and SQLite-consistent backup download actions by invoking the
  packaged ReefProof CLI rather than duplicating its behavior.
- Reuse `./reefproof serve --no-open --no-reload` and `/workbench` in both
  development and future packaged execution.
- Add repository-owned run, build, and focused-test commands.
- Package one unsigned macOS `.app` with the existing ReefProof binary and
  project version. Do not add installers, signing, updates, renderer APIs,
  HYDROS connectivity, internet probing, restore controls, or notebook feature
  changes. HYDROS and MQTT states are display-only values reported by the local
  ReefProof status endpoint.

## Risks

- A desktop window can accidentally broaden renderer privileges or navigation.
- A launcher can orphan its loopback server on abnormal shutdown.
- Native actions can accidentally bypass CLI validation or mislabel a local
  listener as live HYDROS connectivity.
- Packaged execution needs the existing ReefProof binary and web assets beside
  Electron; this slice does not create a platform installer.

## Evaluation

- Focused Node tests cover BrowserWindow security options, navigation and child
  window denial, repository wiring, and deterministic child termination.
- TypeScript compilation covers the Electron main process.
- Human acceptance runs `make run/desktop`, inspects the Workbench and renderer
  globals, captures a 1440 x 1000 screenshot, closes Electron, and confirms no
  owned processes remain.
- Run the canonical local quality gate after focused evidence is stable.

## Completion criteria

- The desktop commands build, test, and launch the existing Workbench.
- Renderer Node integration is disabled and no preload or IPC bridge exists.
- Same-origin Workbench navigation works; unexpected navigation and child
  windows are denied.
- Closing Electron terminates the server it started.
- Native menus report build identity, local-service reachability, and separate
  HYDROS/MQTT observation states; operators can restart the owned service, run
  offline diagnostics, and save a new verified backup without overwriting a
  file.
- Documentation states prerequisites and packaging limitations truthfully.
- Pull requests and `main` builds produce an unsigned macOS application archive
  only after the delivery quality gate passes.

## Open questions

- Signing, notarization, installer format, release publication, and non-macOS bundles remain future
  decisions.
