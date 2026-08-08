# v0.1.0 Release Criteria

This document defines the v0.1.0 product and evidence contract. Future release
integration points belong in `docs/roadmap.md`.

## Product boundary

v0.1.0 is an offline assurance workbench that runs locally or as an explicitly
configured private-LAN LXC-hosted service. It accepts bundled synthetic
authored fixtures, explicit manual evidence, and operator-supplied files without
contacting HYDROS. Every mock or manual result is labeled as such.

HYDROS remains runtime authority. v0.1.0 must not connect to HYDROS, publish
MQTT, change equipment or controller state, perform automatic remediation, or
expose a general-purpose mutation or host-administration interface.

## User-visible capability

- The standalone CLI reports version/build identity and offers command-specific
  help without a source checkout.
- Attached-terminal `./reefproof` provides a discoverable starter menu and
  registry-derived command completion while explicit and redirected commands
  remain non-interactive.
- `snapshot`, `graph`, `check`, and `explain` produce deterministic offline
  evidence with provenance and `PASS`, `FAIL`, or `UNKNOWN` outcomes.
- `infra-smoke` exercises the credential-free persistence scenario.
- `database schema|inspect|verify|backup|restore` provides bounded SQLite
  operations. Backup and restore never overwrite an existing destination.
- Fresh v0.1 databases migrate directly to the single release-schema baseline.
  Pre-release development databases are unsupported; ReefProof fails closed
  rather than upgrading or deleting them. The release schema requires valid
  canonical JSON, balanced evaluation summaries, bounded invariant enums, and
  typed operator-session columns without a duplicate session document.
- Local `serve` exposes the authenticated Workbench only on loopback. The hosted
  deployment profile exposes it only on an explicit private-LAN address with no
  public ingress.
- Manual Workbench evidence retains `MANUAL / NOT LIVE` provenance through
  rendered and serialized representations.
- The Electron shell is named ReefProof and supports explicit, mutually
  exclusive `local-managed` and `remote-hosted` modes with no silent fallback.
- Local mode owns only its bundled loopback service. Remote mode starts no local
  runtime or evidence store and treats the configured hosted backend as
  authoritative.
- Both modes display connection mode, exact authoritative origin, build/service
  status, and HYDROS/MQTT observation state without conflation.
- Both modes provide bounded diagnostics, restart, and SQLite-consistent backup.
  Remote backup is created on the hosted service, downloaded through an
  authenticated fixed-purpose API, integrity-checked, and saved to a
  user-selected desktop destination.

## LXC hosting contract

- The exact v0.1.0 OCI artifact runs on the target Proxmox LXC by immutable
  digest with a durable data directory and an explicit private-LAN listener.
- Existing identity-bound sessions authenticate every hosted operation.
- Diagnostics, backup creation/download, and accepted lifecycle actions use
  versioned, fixed-purpose, authorized, and audited APIs.
- No request accepts arbitrary commands, paths, service names, containers,
  hosts, supervisor arguments, SQL, or general LXC/Proxmox operations.
- Restart delegates to one narrow ReefProof supervisor adapter and proves
  service recovery plus evidence persistence.
- HTTP is allowed only for a validated literal private address and is visibly
  labeled reduced-security transport. Public, loopback-as-remote, link-local,
  metadata, multicast, unspecified, reserved, credential-bearing, malformed,
  and redirected destinations fail closed before credentials are sent.

## Artifact contract

- `pyproject.toml` version `0.1.0`, Git tag `v0.1.0`, CLI identity, OCI metadata,
  and desktop bundle versions must agree.
- `make build` must start from a clean tree and verify the standalone artifact,
  OCI image, SPDX SBOM, build manifest, and checksums.
- `make build/desktop-app` must build the embedded executable from the exact
  committed revision and verify the unsigned macOS application bundle.
- Runtime artifacts must exclude tests, development-only dependencies,
  credentials, local databases, logs, snapshots, and other private evidence.
- The OCI image runs as a non-root user with an explicit writable data mount;
  deployment uses an immutable digest.

## Release-candidate definition of done

Every item below is mandatory for the exact v0.1.0 candidate commit:

- The canonical source quality gate passes after the final source change.
- Attached-TTY acceptance covers affected CLI/menu workflows.
- Browser acceptance covers affected Workbench routes, authentication, and
  generated contracts.
- Desktop tests and packaged-app verification cover lifecycle ownership,
  mode separation, origin validation, status labeling, dialogs, backup behavior,
  and renderer/navigation isolation.
- Attached desktop acceptance covers both exact modes. Remote acceptance proves
  zero local process/data activity and authenticated backup download to the
  selected local destination.
- Target-LXC acceptance proves first boot, authenticated Workbench access,
  diagnostics, backup/download, restart recovery, and durable evidence across
  both service and LXC restart.
- Standalone CLI and OCI smoke tests execute from built artifacts.
- Structural checks prove the absence of HYDROS mutation and MQTT publication.
- The candidate commit is clean and exact; unknown or untested evidence is not
  reported as passing.

Local evidence does not prove hosted CI, target-LXC acceptance,
vulnerability-scan results, signing, notarization, publication, or live-system
behavior. The v0.1.0 candidate requires target-LXC acceptance; the other
external evidence remains separately classified.

## Explicit exclusions

v0.1.0 does not promise:

- live HYDROS/AWS observation or live Home Assistant delivery;
- public-Internet Workbench access, endpoint discovery, or LAN scanning;
- signed/notarized apps, installers, automatic updates, universal binaries, or
  non-macOS desktop packages;
- a supported detached-daemon compatibility contract across platforms;
- automatic trust remediation or generalized SQL/filesystem administration; or
- public compatibility beyond the platforms verified for the release.
