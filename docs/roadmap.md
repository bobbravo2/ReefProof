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

## v0.2 — controlled feedback and deployment hardening

v0.2 may add TLS/private-overlay requirements, connection-profile usability,
expanded platform packaging, signed/notarized distribution, and controlled
community preview. It must preserve v0.1's exclusive modes, backend authority,
fixed-purpose operational APIs, and prohibition on general host or HYDROS
control.

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
