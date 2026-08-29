# ReefProof Roadmap

This roadmap describes release integration points, not transient implementation
status. Current evidence and the next engineering task live under `.agent/`;
dated implementation plans live under `docs/plans/`.

## v0.1.0 — offline assurance, locally or LXC-hosted

v0.1.0 establishes ReefProof's read-only, offline product boundary:

- a discoverable CLI and attached-terminal starter menu;
- deterministic normalization of bundled authored fixtures and explicit offline
  operator exports;
- typed reliability graphs and versioned `PASS`, `FAIL`, and `UNKNOWN`
  invariant evaluation;
- durable SQLite evidence with integrity verification, backup, and restore;
- a loopback-only authenticated Workbench for manual, clearly provenance-labeled
  assurance evidence;
- an explicitly configured private-LAN LXC hosting profile with durable evidence,
  authenticated operations, and no public ingress;
- a hardened OCI image, standalone CLI artifact, and unsigned macOS
  `ReefProof.app` package; and
- dual-mode desktop operation: `local-managed` owns a bundled loopback service,
  while `remote-hosted` connects only to the selected LXC ReefProof origin;
- build identity, authoritative-origin status, offline diagnostics, bounded
  restart, and SQLite-consistent backup creation and download in both modes.

The v0.1.0 release does not connect to HYDROS, publish MQTT, control equipment,
perform automatic remediation, permit public ingress, ship an installer, or
claim signed/notarized desktop distribution. ReefProof service reachability is
not evidence of HYDROS or MQTT connectivity.

Release integration points:

- `pyproject.toml` is the version authority.
- `make check` is the complete source quality gate.
- `make build` produces and verifies the CLI/OCI distribution bundle, SBOM,
  manifest, and checksums.
- `make build/desktop-app` builds the embedded CLI from committed `HEAD`,
  packages the unsigned macOS app, and verifies bundle identity.
- Private-LAN target-LXC acceptance must prove durable evidence across restart,
  authenticated fixed-purpose operations, remote backup download, and exact
  desktop mode separation.
- Tag, hosted CI, signing, notarization, publication, and deployment evidence
  remain separate from local build evidence.

## v0.1.1 — packaged Workbench hotfix

v0.1.1 repairs the packaged browser application without broadening the v0.1
product boundary. The tracked Workbench bundle is a required release input, and
release acceptance verifies the actual OCI image and browser-critical assets
rather than relying on source-checkout tests alone.

## v0.1.2 — authored commissioning vertical slice

v0.1.2 adds one bounded production data spine for the Primary Reef System:

```text
read-only Google Sheets authored source
-> immutable import evidence
-> explicit human acceptance
-> ReefProof-owned canonical identity
-> evidence-backed commissioning
-> deterministic P-touch label CSV
```

This release is still pre-live-observation ReefProof. Google Sheets supplies
authored intent only; it is not runtime evidence and cannot silently mutate
canonical state. HYDROS remains offline evidence supplied explicitly by an
operator. ReefProof does not write to Sheets, connect to a living HYDROS system,
publish MQTT, control a printer, or perform automatic remediation.

The detailed product and architecture contract is the accepted
`docs/plans/2026-08-16-v0.1.2-modular-workbench-sheets-commissioning-labels.md`.
Implementation breadth is not acceptance. v0.1.2 is complete only when one
production-shaped flow proves all of the following together:

- exactly the six accepted Sheet tabs are fetched server-side with read-only
  credentials and strict schema, reference, provenance, and secret boundaries;
- changed, invalid, conflicting, and removed authored records remain reviewable
  and never overwrite accepted or proven ReefProof state automatically;
- source-to-canonical identity bindings survive source renames and outages;
- authored and observed evidence remain separate and blocking contradictions
  feed the commissioning projection rather than defaulting to no conflict;
- every applicable power, communications, failure-mode, fault-test, connection,
  and label requirement is backend-derived as `PASS`, `FAIL`, or `UNKNOWN`;
- one removable cable produces deterministic `FROM / TO / CABLE` output for
  both ends and cannot be commissioned before both physical verifications;
- the Workbench is page-owned, generated contracts match OpenAPI, and the same
  served application passes real browser and Electron acceptance; and
- a clean candidate passes source, browser, packaged artifact, secret-boundary,
  backup/replay, and target-LXC acceptance.

Incomplete slices remain WIP even when their models, routes, tables, or fixture
tests exist. Current status and exact slice ownership remain in `.agent/` so the
roadmap does not become a second implementation ledger.

## v0.2.0 — controlled preview and deployment hardening

v0.2.0 turns the accepted commissioning slice into a supportable preview. It
must not absorb unfinished v0.1.2 acceptance work or become the first live
HYDROS release. Begin only from an accepted v0.1.2 candidate.

### Slice 1 — security profiles and credential operations

- Define supported loopback, private-LAN TLS, and private-overlay connection
  profiles with explicit trust and reduced-security presentation.
- Establish deployable Google credential provisioning, rotation, revocation,
  failure, and backup/restore procedures without exposing credentials to the
  browser, SQLite evidence, logs, metrics, or release artifacts.
- Preserve fixed-purpose hosted operations and reject arbitrary host, path,
  service, command, SQL, or controller input.

Exit gate: local-managed and remote-hosted desktop acceptance proves origin,
session, credential, redirect, outage, restart, and durable-evidence behavior
for every supported profile.

### Slice 2 — installation and platform distribution

- Expand supported platform artifacts only where automated packaged acceptance
  is available.
- Add signing, notarization, installation, upgrade, rollback, and artifact
  identity checks as platform-specific contracts rather than generic claims.
- Preserve deterministic source/binary/OCI domain-result parity and publish
  human release notes alongside immutable digest, SBOM, vulnerability, and
  provenance evidence.

Exit gate: a clean candidate is installable and recoverable on every claimed
platform, and each published artifact is traceable to the accepted source
revision and release notes.

### Slice 3 — controlled community preview

- Provide bounded onboarding, example authored-source schemas, commissioning
  guidance, diagnostics, backup/restore, and an explicit support boundary.
- Collect feedback through opt-in, human-readable channels; do not add ambient
  telemetry, private evidence upload, or remote administration by default.
- Distinguish product defects, unsupported workbook schemas, missing operator
  evidence, and unavailable external services in user-facing diagnostics.

Exit gate: a new operator can install ReefProof, connect an authorized
read-only authored source, review changes, preserve evidence, export labels,
and recover from failure without developer-only intervention.

### Slice 4 — preview hardening and promotion

- Exercise schema evolution, upgrade/rollback, source outage, credential
  rotation, database backup/restore, and immutable release rollback.
- Bound logs, metrics, mutation audits, retained source evidence, and support
  bundles against secrets and private system identifiers.
- Promote only capabilities with current unit, integration, browser, packaged,
  and deployment evidence; retain `UNKNOWN` for untested external behavior.

Exit gate: the controlled preview has an explicit support matrix, no unresolved
release-blocking safety or data-loss defects, and a repeatable publication and
recovery process.

Across every v0.2.0 slice, preserve v0.1's exclusive desktop modes, backend
authority, append-only evidence, explicit human acceptance, fixed-purpose
operational APIs, and prohibition on general host or HYDROS control.

## v0.3 — authorized live observation

v0.3 is the earliest release that may observe a living HYDROS system. It
requires a separately accepted transport ADR and explicit owner authorization.
The product must:

- distinguish application reachability, HYDROS observation, and MQTT
  observation as separate states;
- represent `UNKNOWN`, `OFFLINE`, `DISABLED`, and stale data explicitly;
- keep browsers and Electron isolated from direct HYDROS or MQTT access;
- prove credential redaction, disconnect behavior, stale-data handling, and
  the structural absence of writes; and
- retain HYDROS as runtime authority with no automatic remediation.

Later product work must be justified by an accepted operator problem and its
evidence contract. It is intentionally omitted from this release roadmap until
that decision exists.
