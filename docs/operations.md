# ReefProof v0.1.0 Operations Contract

This contract covers the offline CLI, local and private-LAN LXC-hosted
Workbench, SQLite evidence, standalone artifact, OCI image, and unsigned
dual-mode macOS desktop package.

## Safety and authority

HYDROS remains runtime authority. ReefProof v0.1.0 has no live HYDROS transport
and must not publish MQTT, mutate controller or equipment state, or perform
automatic remediation.

The selected backend is authoritative for Workbench authentication, policy, and
evidence. Electron is presentation and bounded lifecycle glue for either its
bundled loopback service or one explicit private-LAN ReefProof origin; it
receives no controller or general host authority.

## Local data

`REEFPROOF_DATA_DIRECTORY` selects the runtime data directory. The OCI default
is `/var/lib/reefproof`; source-development defaults remain repository-local and
Git-ignored. A Git-ignored path is not a backup.

The database is `reefproof.sqlite3` and uses SQLite WAL mode. Keep the data
directory writable even when the application or container root is read-only.
v0.1 establishes a fresh-install schema baseline. Databases created by
unreleased development revisions are not supported or migrated. Preserve the
original offline exports, move an incompatible development database aside, and
let the v0.1 application create a new database; ReefProof does not delete or
silently adopt the old file.

The v0.1 schema stores operator sessions only in typed columns. Canonical JSON
is retained for snapshots and immutable domain evidence, where SQLite validates
that each document is well-formed. Evaluation summary counts remain alongside
prunable result detail by design.

Use the fixed database commands instead of a general SQL console:

```bash
reefproof database schema
reefproof database inspect
reefproof database verify
reefproof database backup /safe/new/reefproof-backup.sqlite3
reefproof database restore /safe/reefproof-backup.sqlite3 /new/reefproof.sqlite3
```

`inspect` accepts no SQL. `backup` uses SQLite's backup API, verifies integrity,
and atomically creates a new destination. `restore` verifies the source and
schema, creates a new target, reopens it, and checks the persisted evidence
view. Neither operation overwrites an existing path.

For an emergency filesystem copy, stop every ReefProof process and copy the
main database, `-wal`, and `-shm` files as one set whenever sidecars exist.
Never copy only the main file from a live database.

## Local Workbench

```bash
reefproof serve
reefproof serve --no-open
reefproof serve --project-id primary-reef-system
```

Local-managed Workbench sessions bind only to loopback. A separate hosted
deployment profile may bind on the target LXC's private-LAN interface. It must
not accept public ingress or be exposed through an unreviewed reverse proxy.

### Authentication and session lifecycle

At startup the service uses the configured bootstrap shared secret or prints a
generated one to the terminal. The initial secret establishes a session and
enables authenticator app enrollment; subsequent sessions require a six-digit authenticator code.
Secrets and authenticator app values are not stored as evidence provenance.

**Session expiry:** Restarting the service invalidates all existing frontend
sessions. Each session is process-local and bound to the current authenticator app
enrollment state; after HYDROS restart or ReefProof service restart, the
operator must re-authenticate using the active method (bootstrap secret for
first login, authenticator code for returning logins).

**First-login to enrollment lifecycle:**

1. Operator starts ReefProof (`reefproof serve` or hosted deployment)
2. Workbench login screen auto-selects "Bootstrap shared secret"
3. Operator retrieves the bootstrap secret:
   - **Local:** Copy from terminal startup output
   - **Hosted:** Retrieve from the operator Vault without printing or recording
4. Operator authenticates with bootstrap secret and gains workbench access
5. In an unlocked workbench, operator navigates to the sessions page and
   enrolls their authenticator app:
   - Click "Enroll authenticator app"
   - Scan the QR code or manually enter the seed in their authenticator app
   - Confirm enrollment with a fresh six-digit code
6. After successful enrollment, the bootstrap secret no longer establishes
   sessions; authenticator app becomes the exclusive authentication method
7. For all subsequent sessions, operator selects "Authenticator code" and enters
   the current six-digit code from their phone

**Re-enrollment after seed loss:**

If the authenticator seed is lost:
1. Operator runs `reefproof auth totp reset` on the LXC or local system
2. This invalidates all existing sessions and re-enables bootstrap-secret login
3. Operator repeats the enrollment process with a new authenticator device

The attached-terminal launcher and `daemon` commands preserve process
ownership. ReefProof may open an unmanaged valid Workbench but will not stop or
restart it; a foreign listener blocks startup. Explicit commands and redirected
input remain non-interactive and preserve child exit status.

## Offline assurance

`snapshot`, `graph`, `check`, and `explain` use local inputs only. Bundled
fixtures are synthetic and labeled `AUTHORED`; manual Workbench results retain
`MANUAL / NOT LIVE`. Imported fields and relationships remain `UNKNOWN` unless
their semantics are explicitly validated.

`infra-smoke --format json` is credential-free and network-free. It creates and
then verifies deterministic synthetic evidence, including database integrity
and deduplication. All command state remains beneath
`REEFPROOF_DATA_DIRECTORY`.

Operator-supplied exports are private evidence. Keep originals and normalized
outputs outside Git, record a timezone-aware capture time and SHA-256, and do
not repair or reformat original bytes. The offline importer does not authorize
live transport or undocumented vendor semantics.

## Standalone and OCI bundle

Run the complete local bundle from a clean committed tree:

```bash
make build
```

The build stages allowlisted tracked inputs under `.build/`, creates the
standalone CLI and versioned archive, builds and smoke-tests the OCI image, and
writes the SPDX SBOM, build manifest, image receipt, and `SHA256SUMS` beneath
`dist/`. `scripts/build-verify.py` verifies checksums and identity metadata.

The OCI image defaults to `version`, runs as the unprivileged `reefproof` user,
and expects a writable volume at `/var/lib/reefproof`. A hardened offline smoke
invocation is:

```bash
podman run --rm --read-only --read-only-tmpfs=false \
  --tmpfs /tmp:rw,noexec,nosuid,nodev --network=none --cap-drop=all \
  --volume reefproof-data:/var/lib/reefproof \
  ghcr.io/bobbravo2/reefproof@sha256:DIGEST infra-smoke --format json
```

The image does not publish ports, select host interfaces, or supervise itself.
The LXC supervisor owns private-LAN publication, authentication exposure, and
lifecycle. A representative container invocation is:

```bash
podman run --detach --name reefproof-workbench \
  --restart=always \
  --read-only \
  --volume reefproof-data:/var/lib/reefproof \
  --publish PRIVATE_LXC_ADDRESS:8787:8787 \
  --env REEFPROOF_HOSTED_RESTART_MODE=supervised-self-terminate \
  IMAGE serve --bind 0.0.0.0 --port 8787 --no-open
```

`PRIVATE_LXC_ADDRESS` must be an explicit address assigned to the private LXC;
do not substitute `0.0.0.0` as the host publication address. Removing or
replacing the data volume can destroy evidence; create and verify a backup
before volume maintenance.

`supervised-self-terminate` is accepted only when ReefProof runs in production.
It terminates only the ReefProof process after an authenticated `202` restart
response. The external `--restart=always` policy restores the service; ReefProof
has no host or container-management API. Do not replace this with a caller-
supplied command or a privileged container socket.

### Target-LXC hosting acceptance

The v0.1.0 candidate is not complete until the exact immutable OCI artifact is
accepted on the target Proxmox LXC:

1. Configure no public ingress, an explicit private-LAN listener, and durable
   storage mapped to `/var/lib/reefproof`.
2. Establish an identity-bound operator session from the desktop's configured
   `remote-hosted` origin.
3. Verify Workbench status and bounded diagnostics execute on the hosted side.
4. Create a SQLite-consistent hosted backup, retrieve it through an authenticated
   opaque identifier, save it to the desktop's selected destination, and verify
   integrity after transfer. Reject path input, traversal, and unauthorized or
   unknown identifiers.
5. Request restart only through the allowlisted ReefProof supervisor adapter;
   verify recovery and unchanged durable evidence after service restart.
6. Restart the LXC and repeat status, storage integrity, and evidence-persistence
   checks.
7. Prove the hosted APIs accept no arbitrary commands, paths, service names,
   containers, hosts, SQL, or Proxmox/LXC operations.
8. Prove public/special-use origins and cross-origin redirects receive no
   credentials or requests from the desktop.

Published OCI releases use `ghcr.io/bobbravo2/reefproof` and immutable digests.
The tag, package version, CLI identity, and OCI metadata must agree. Hosted
release automation must record provenance, SPDX SBOM, vulnerability results,
and the registry-reported digest. No local build proves publication or hosted
attestation success.

## Electron desktop

Development prerequisites include Node.js 22.12 or newer, locked npm
dependencies, and the normal Python toolchain.

```bash
make run/desktop
make test/desktop
make build/desktop-app
make run/desktop-app
```

`make run/desktop` recompiles source and uses Electron's development host bundle;
macOS may label that host application `Electron`. The packaged application is
named ReefProof and is written beneath:

```text
dist/desktop/ReefProof-darwin-<node-arch>/ReefProof.app
```

Packaging builds the embedded ReefProof executable from exact committed `HEAD`
in an isolated temporary worktree, compiles the Electron main process, embeds
the ReefProof icon, normalizes timestamps, and verifies application version,
bundle identity, and executable revision. It does not reuse a stale standalone
artifact or include uncommitted source changes.

The app supports mutually exclusive `local-managed` and `remote-hosted` modes.
Local mode starts and owns one loopback Workbench. Remote mode connects to the
configured private-LAN ReefProof origin and must not launch a local process,
create local evidence, inspect a local PID, or silently fall back to loopback.

The window displays mode and exact authoritative origin. Application/build,
ReefProof-service, HYDROS-observation, and MQTT-observation states remain
separate. Both modes expose bounded diagnostics, restart, and backup. Local
backup uses the native directory picker and CLI backup operation. Remote backup
uses authenticated hosted creation and download APIs, then writes the verified
artifact to the explicit user-selected local destination. Human dialogs
summarize results rather than displaying raw JSON.

The renderer is sandboxed with Node integration disabled and receives no
filesystem, shell, process, preload, or IPC authority. Navigation and child
windows remain restricted by the desktop security policy.

The v0.1.0 app is unsigned and unnotarized. There is no DMG, installer,
automatic updater, universal binary, or non-macOS desktop package. Crash,
forced-kill, and operating-system shutdown behavior remains
platform-dependent until separately accepted.

## Release acceptance

For the exact candidate commit:

1. Require a clean worktree and matching `0.1.0` version identity.
2. Run `make check` after the final source change.
3. Run `make build` and retain its verified manifest, SBOM, and checksums.
4. Run `make build/desktop-app` and verify the packaged app identity.
5. Exercise affected CLI paths through attached `./reefproof` TTY and affected
   Workbench paths through the running browser interface.
6. Exercise the packaged desktop in both modes, including authoritative origin,
   authentication, diagnostics, backup download, restart, and failure routes.
7. Complete the target-LXC acceptance above using the exact immutable artifact.
8. Verify artifacts contain no credentials, local databases, snapshots, logs,
   private exports, or development-only test payloads.
9. Record hosted CI, vulnerability scan, publication, signing/notarization, and
   deployment evidence separately. Unperformed checks are `NOT TESTED`.

This acceptance proves offline ReefProof behavior only. It does not authorize
live HYDROS access, MQTT publication, equipment control, or remediation.
