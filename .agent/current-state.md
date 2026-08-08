# Current State

Last updated: 2026-08-08

## Current gate

The v0.1 release candidate requires both the first offline electrical-assurance
slice and the dual-mode hosted deployment contract. Secret-bearing input must
remain protected. The exact immutable OCI artifact must run on the private-LAN
target LXC, and the packaged desktop must pass `local-managed` and
`remote-hosted` acceptance without mixing process, storage, or authority.

## Current capability

- Offline fixtures and the private export normalize into deterministic evidence.
- Typed reliability graphs and fifteen invariants preserve `PASS`, `FAIL`, and
  `UNKNOWN` with explanations and provenance.
- SQLite stores configuration snapshots, evaluation runs/results, finding transitions,
  return-flow policy revisions,
  authority chains, and schema migrations.
- The pre-release migration chain is consolidated into one fresh-install v0.1
  schema contract. Old development databases are intentionally unsupported;
  normalized source exports remain the rebuild boundary.
- The local CLI, loopback Workbench, OCI image, and unsigned macOS Electron shell
  exist without live HYDROS access, MQTT publication, controller mutation, or
  automatic remediation.
- All non-presentation APIs are versioned under `/v1`; the canonical system
  surface includes correlated status, health, metrics, findings, local OpenAPI,
  and a self-contained read-only API reference.
- ADR 0008 is accepted. Its exhaustive route, authentication, authorization,
  audit, and success-status matrix is enforced by the Python integration suite.
- Dual-mode desktop, authenticated hosted operations, immutable API mutation audit,
  opaque single-use backup download, bounded staging retention, and narrow
  supervisor-owned restart are implemented locally. Packaged dual-mode and
  target-LXC acceptance remain required release evidence.

## Current evidence

- The accepted `RP-UNIT-001` result confirms the observed HYDROS `tempFmt` value
  `"1"` means expected Fahrenheit; other vendor semantics remain unknown.
- The last committed local quality and artifact gates passed before the current
  dual-mode implementation began. They must be rerun after that slice is
  complete; prior timings and test counts are not current release evidence.
- The database and interface contracts have local Python, browser, and desktop
  coverage plus generated-contract parity. The current shared-tree Python run
  is not green while the concurrent session-dependency work is being reconciled,
  and its 15-second wall-clock service budget remains unmet. The final canonical
  quality gate, clean-tree bundle, packaged desktop, and target-LXC acceptance
  remain required.
- No v0.1 release candidate has been accepted, pushed, tagged, published, or
  deployed.

## Blocking unknowns

- Safe allowlisted Tuya fields required for topology.
- Physical-port relationships and authored circuit, protection, backup-power,
  and load mappings.
- Accepted `lowPower` and `maxOnTime` semantics.
- Packaged acceptance in both exact desktop modes.
- Immutable-image target-LXC persistence and restart acceptance.

## History

The previous cumulative implementation and verification ledger is archived at
`docs/archive/current-state-2026-08-01.md`. Dated plans, ADRs, and Git history
remain authoritative for completed work; this file contains only context needed
for the current gate and handoff.
