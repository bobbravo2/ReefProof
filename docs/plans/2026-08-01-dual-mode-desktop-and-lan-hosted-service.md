# Dual-mode desktop and LAN-hosted service

Status: Implemented locally; packaged desktop and target-LXC acceptance pending

## Outcome

Implement ADR 0007 so the Electron desktop can either own the existing local
loopback ReefProof service or connect to an explicitly configured ReefProof
service on a private Proxmox LXC address and port. In remote mode, the hosted
backend remains authoritative and executes bounded status, diagnostics, backup,
and supported ReefProof lifecycle operations.

## Scope

### Desktop connection model

- Add an explicit `local-managed` or `remote-hosted` mode with no automatic
  fallback between them.
- Add a dedicated remote service origin setting; do not reuse the backend bind
  address as a client destination.
- Accept a direct private LXC IP and explicit port. Keep DNS optional.
- Validate the origin before any network request. Allow HTTP only for a literal
  private address; reject public and special-use targets, credentials,
  fragments, malformed URLs, and cross-origin redirects.
- Keep the renderer sandboxed and restrict navigation and resource authority to
  the selected backend origin.
- Display connection mode, authoritative origin, authentication state, and
  reduced-security HTTP status clearly.

### Runtime separation

- Preserve current local daemon ownership and local operations in
  `local-managed` mode.
- In `remote-hosted` mode, never launch or invoke the packaged ReefProof binary,
  create a local data directory, inspect a local PID file, or silently connect
  to a loopback service.
- Terminate the existing browser session before changing mode or origin.
- Ensure packaged runtime state is stored outside application resources in
  local mode and cannot be copied into a distributable application bundle.

### Hosted operational APIs

- Define versioned, authenticated endpoints for hosted status, bounded
  diagnostics, verified backup creation, authenticated backup retrieval, and
  supported ReefProof service lifecycle requests.
- Reuse existing identity-bound operator sessions and authorization rules.
- Represent requests and results with generated typed contracts.
- Execute fixed ReefProof operations only. Reject arbitrary commands,
  executables, service names, paths, hosts, and supervisor arguments.
- Record authenticated actor, operation, target ReefProof instance, timestamp,
  outcome, and bounded failure detail without storing credentials.
- Delegate lifecycle actions through one allowlisted ReefProof supervisor
  adapter suitable for the target LXC deployment. Do not expose general
  systemd, Podman, LXC, Proxmox, or shell access.

### LXC deployment contract

- Configure the hosted service with an explicit private-LAN listener, durable
  data directory, existing operator-session authentication, and no public
  ingress.
- Preserve backend authority for storage, diagnostics, backup, and operational
  actions.
- Define the supervisor behavior needed for restart without granting the
  application unrestricted host control.
- Keep live HYDROS, MQTT publication, automatic remediation, and controller
  mutation outside scope.

## Non-goals

- Public Internet exposure, public-host HTTP, automatic endpoint discovery, or
  LAN scanning.
- A second desktop identity system, locally persisted operator credentials, or
  identity supplied by the renderer.
- Implicit synchronization, merge, or migration between local and hosted
  evidence stores.
- General remote administration, terminal access, arbitrary SQL, arbitrary
  filesystem browsing, container management, or Proxmox control.
- Direct desktop or browser communication with HYDROS, CoralVue, MQTT, Home
  Assistant, or other equipment transports.

## Risks and mitigations

- **Cleartext LAN sessions:** HTTP can expose login and session traffic. Limit
  it to validated literal private addresses, show a persistent warning, avoid
  credential persistence, and document TLS or a trusted overlay as the upgrade
  path.
- **Server-side request or redirect escape:** Centralize origin validation,
  resolve and classify every destination before request, reject redirects, and
  test zero-request failure for rejected targets.
- **Split-brain evidence:** Make modes exclusive, prevent local runtime startup
  in remote mode, and display the authoritative origin on every primary page.
- **Overbroad operational API:** Use fixed schemas and allowlisted adapters;
  reject all caller-selected commands, paths, services, and infrastructure
  identifiers.
- **Restart response interruption:** Model restart as a requested operation with
  an identifier, then verify recovery through a bounded status probe rather
  than relying on one uninterrupted HTTP response.
- **Packaged private-state leakage:** Move runtime data outside application
  resources and add artifact rejection tests for credentials, databases, logs,
  snapshots, and `.local` paths.
- **Session confusion across origins:** Clear cookies and renderer state on
  origin change and require fresh backend authentication.

## Implementation sequence

1. Define typed desktop mode/origin configuration and private-origin
   validation with focused failure tests.
2. Separate local runtime ownership from remote connection behavior and prove
   remote mode performs no local process or data operation.
3. Specify and generate authenticated operational API contracts with fixed,
   bounded request and response models.
4. Implement hosted status, diagnostics, verified backup creation, and
   authenticated backup download with audit evidence before lifecycle transitions.
5. Add the narrow supervisor adapter and asynchronous restart/recovery
   verification for the target LXC service.
6. Wire Electron menus and Workbench presentation to the backend operations,
   including authoritative-origin and HTTP-risk indicators.
7. Repair the packaged data-directory boundary and add distribution artifact
   privacy acceptance.
8. Run local, remote-fixture, packaged-desktop, and target-LXC acceptance, then
   execute the applicable deterministic repository gate.

## Evaluation

- Focused Python and Node tests for address classification, endpoint parsing,
  navigation, redirects, mode transitions, session clearing, and the absence of
  local execution in remote mode.
- API integration tests for authentication, authorization, audit records,
  bounded diagnostics, verified backup behavior, lifecycle request/recovery,
  and rejection of arbitrary operational inputs.
- Attached Electron acceptance in both modes, including authentication,
  status, diagnostics, backup, restart, mode switching, and failure routes.
- Packaged `.app` inspection proving no `.local`, TOTP state, SQLite data,
  snapshots, logs, or private paths are present.
- Private-LAN target-LXC acceptance using the exact configured IP and port,
  followed by persistence and restart verification.
- Safety checks for the permanent no-HYDROS-mutation and no-MQTT-publication
  boundaries.
- The repository-owned final local-CI gate after the last implementation
  change.

## Completion criteria

- Operators can deliberately select local managed or remote hosted mode and
  always see which ReefProof instance is authoritative.
- A direct private LXC IP and port works; public and special-use destinations,
  unsafe URL forms, and redirects fail before credential forwarding.
- Remote mode never starts or invokes a local ReefProof runtime and never uses
  a local evidence store for hosted operations.
- Existing operator sessions authenticate and authorize all hosted operations.
- Status, diagnostics, backup, and accepted lifecycle actions execute on the
  LXC side through fixed-purpose, audited APIs.
- No API accepts arbitrary commands, paths, services, containers, hosts, or
  infrastructure operations.
- The packaged desktop contains no runtime credentials or private evidence.
- Both exact desktop modes and the target LXC pass current interface acceptance
  and the final repository gate.
- Documentation labels HTTP private-LAN transport risk accurately and makes no
  public-hosting, live-HYDROS, or automatic-remediation claim.

## Open questions

- Where should desktop connection profiles be stored, and which non-secret
  fields may persist across launches?
- What certificate and trust-store policy will replace private-LAN HTTP when
  TLS is introduced?
