# Next Task

## Outcome

Complete and accept the v0.1 dual-mode desktop and private-LAN target-LXC
vertical slice defined by ADR 0007.

## Completion criteria

- `local-managed` retains exclusive ownership of its bundled loopback runtime.
- `remote-hosted` connects only to the explicit private-LAN ReefProof origin and
  performs no local runtime, PID, database, or evidence-store operation.
- Identity-bound sessions protect fixed-purpose hosted diagnostics, backup
  creation/download, and accepted restart operations; every operation is audited.
- Remote backup downloads a verified SQLite artifact to the user-selected local
  destination through an opaque identifier with no path authority.
- The exact immutable OCI artifact passes target-LXC first boot, persistence,
  backup/download, service restart, and LXC restart acceptance.
- Both packaged desktop modes, the canonical quality gate, complete bundle, and
  artifact privacy checks pass from one clean candidate commit.

## Boundary

No public ingress, endpoint discovery, silent mode fallback, general host/LXC
administration, direct HYDROS access, MQTT publication, equipment control, or
automatic remediation. Preserve the separate secret-safe electrical-assurance
gate; dual-mode hosting does not satisfy it.
