# ADR 0007: Dual-Mode Desktop and LAN-Hosted Service

- Status: Accepted; required for the v0.1.0 release candidate
- Date: 2026-08-01
- Decision owner: Customer 0
- Scope: Desktop-to-service topology, private-LAN reachability, authentication,
  and remote operational actions
- Supersedes: ADR 0004's loopback-only reachability constraint; ADR 0004's
  identity, authorization, and session requirements remain in force

## Context

The current Electron desktop is a local shell around a bundled ReefProof
service. It always loads `http://127.0.0.1:<port>`, starts and owns a local
daemon when that endpoint is unavailable, and invokes the bundled CLI for
diagnostics, backup, and lifecycle actions.

The intended hosted topology runs the authoritative ReefProof service and its
evidence store on a Proxmox LXC host. Operators still need the existing local
desktop workflow, but they must also be able to use the desktop as a client of
that LAN-hosted service. A remote desktop session must not accidentally start
or operate a second local evidence store, and desktop access must not broaden
ReefProof into HYDROS control or general LXC administration.

## Decision

The desktop supports two explicit, mutually exclusive connection modes:

1. **Local managed mode** retains the current loopback topology. The desktop
   starts and owns its packaged ReefProof daemon, loads the loopback Workbench,
   and may invoke local operations through bounded repository interfaces.
2. **Remote hosted mode** connects to one operator-configured ReefProof origin
   on a private LAN. The LXC-hosted backend is authoritative for Workbench
   state, authentication, diagnostics, backups, and supported ReefProof
   lifecycle requests. The desktop does not start, stop, inspect, or write a
   local ReefProof runtime or evidence store in this mode.

Mode and remote origin are explicit desktop configuration. Endpoint discovery,
LAN scanning, fallback from remote to local, and silent origin substitution are
not allowed. A direct LXC IP address and explicit port are supported; stable DNS
is optional rather than required for the first hosted deployment.

### Network boundary

Remote hosted mode is private-LAN-only. It does not authorize public ingress or
Internet-hosted ReefProof.

- HTTPS is accepted for an explicitly configured private-LAN host.
- HTTP is accepted only when the configured host is a literal private address
  validated by ReefProof. Loopback, public, link-local, metadata, multicast,
  unspecified, and reserved destinations fail closed for remote mode.
- URL credentials, fragments, implicit scheme selection, and redirects to a
  different origin are rejected.
- The desktop displays the selected mode and exact authoritative origin before
  authentication and throughout the session.

Allowing HTTP on a trusted LAN is an accepted initial deployment risk. Operator
credentials and session traffic are not transport-encrypted in that mode. TLS
or a trusted private overlay is recommended and becomes mandatory before any
public or untrusted-network exposure.

### Authentication and browser authority

Remote hosted mode uses the existing ReefProof operator-session flow. The
hosted backend establishes, validates, expires, and revokes the identity-bound
session. The desktop does not introduce a second account system, store bearer
credentials, inject identity, or treat a display label as authorization.

The Electron renderer remains sandboxed with Node integration disabled. Main
process navigation, redirects, resource requests, and child windows are
restricted to the configured ReefProof origin except for an explicit external
link handoff to the operating-system browser. Changing origin ends the current
browser session and requires authentication against the newly selected
backend.

### Remote operations

In remote hosted mode, desktop diagnostics, backup, status, and supported
lifecycle actions use versioned, authenticated ReefProof backend APIs. The
operation executes on the LXC-hosted service side and returns structured,
bounded results.

Those APIs expose named ReefProof operations only. They do not accept shell
commands, executable paths, arbitrary database paths, service names, container
arguments, filesystem traversal, or general Proxmox/LXC operations. Lifecycle
actions delegate to a narrowly configured ReefProof service supervisor; they
cannot manage unrelated processes. Backup staging destinations are server-owned
and allowlisted. The desktop retrieves the verified artifact through a separate
authenticated, fixed-purpose download operation and saves it to an explicit
user-selected local destination. The download API accepts an opaque backup
identifier, never a filesystem path.

The v0.1 lifecycle adapter is `supervised-self-terminate`. When explicitly
enabled in a production runtime, an authenticated restart request schedules
termination of only the current ReefProof process after the API response. The
external LXC service manager or container restart policy remains restart
authority. ReefProof receives no systemd, Podman, LXC, Proxmox, shell, or
host-process control capability. Missing, development-mode, repeated, or
unknown restart configuration fails closed.

Hosted backup names contain random UUID identifiers. A successful download
atomically claims the artifact, permits one transfer, and removes the staged
file afterward. Unclaimed artifacts older than 24 hours are removed during the
next backup operation. Callers never supply server paths.

All state-changing ReefProof operations require the existing authenticated and
authorized operator session, append an audit record, and fail closed when the
backend cannot prove authority or completion. Remote operational authority
never includes HYDROS configuration, output, mode, schedule, firmware, MQTT
publication, or automatic remediation.

## Canonical-state impact

Connection mode and selected origin are client configuration, not canonical
reef-system facts. In remote hosted mode the LXC-hosted backend and its evidence
store are authoritative; local cached browser state is presentational only.
Switching modes never merges, copies, or reconciles evidence stores implicitly.

Diagnostics and lifecycle results are operational evidence. Backups copy
existing evidence but do not create or revise canonical project facts.

## Consequences

- The local desktop workflow remains available without an LXC dependency.
- Operators may connect directly to an LXC private IP and port before private
  DNS or TLS is deployed.
- Remote mode needs backend APIs for operations that the desktop currently
  performs by launching its bundled CLI.
- Local and remote modes need visibly different lifecycle and data-directory
  behavior to prevent split-brain evidence.
- HTTP LAN access exposes authentication and session traffic to the trusted
  network and must be presented as reduced transport security.
- Remote service restart is dependent on an external service supervisor and
  must tolerate the connection dropping before a final status response.
- The external supervisor must use a restart-always equivalent; ReefProof
  deliberately cannot restart itself after termination.
- This decision adds no live HYDROS transport and no controller authority.

## Required evidence

- Unit tests for mode selection and strict origin validation, including private
  addresses, public and special-use rejection, alternate ports, malformed URLs,
  URL credentials, fragments, and redirects.
- Electron tests proving remote mode cannot spawn or invoke the local ReefProof
  daemon, diagnostics, database, or backup path.
- Attached desktop acceptance against both a local managed service and a
  private-address hosted test service.
- Authentication tests proving the existing session flow protects every remote
  operation and that changing origin invalidates the desktop's active session.
- Backend tests proving each operational endpoint is fixed-purpose,
  authorized, audited, bounded, and unable to select arbitrary commands,
  processes, paths, containers, or hosts.
- LXC acceptance proving status, diagnostics, backup, and supported lifecycle
  behavior execute on the hosted side and preserve its durable evidence store.
- Backup acceptance proving a remote artifact is created consistently, fetched
  only by an authorized session, saved at the selected desktop destination,
  integrity-checked after transfer, and unavailable through path traversal or
  identifier guessing.
- Network evidence proving no request reaches a rejected or redirected origin.
- Safety checks proving neither desktop mode nor remote operations add HYDROS
  mutation or MQTT publication capability.

## Rejected alternatives

- Replacing local mode with a remote-only desktop: rejected because offline and
  self-contained local operation remains required.
- Treating `REEFPROOF_API_BIND` as the remote destination: rejected because a
  server bind address and a client origin are different security authorities.
- Using an SSH tunnel as the supported desktop architecture: rejected because
  local operational actions would still target the wrong machine and the UI
  could not truthfully represent authority.
- Allowing arbitrary remote URLs or following redirects: rejected because it
  would expose operator credentials and blur the private-LAN boundary.
- Running SSH, shell, Podman, systemd, or Proxmox commands supplied by the
  desktop: rejected because it creates a general-purpose control surface.
- Adding direct desktop-to-HYDROS or browser-to-HYDROS connectivity: rejected
  by the permanent safety boundary.
