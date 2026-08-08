# SRE Deployment Contract

Status: ReefProof-side contract implemented locally; homelab systemd-template
environment forwarding, GHCR publication, and target-LXC acceptance remain
pending.

## Outcome

Provide a deterministic, credential-free offline infrastructure smoke command
and the operational documentation required to run ReefProof's existing
read-only evidence store in a hardened OCI container.

## Scope

In scope:

- `reefproof infra-smoke --format json`, backed only by bundled authored
  fixtures and `REEFPROOF_DATA_DIRECTORY`.
- Idempotent evidence-store initialization, snapshot, evaluation, and finding
  transition verification.
- Schema discovery, integrity checking, and restore verification commands.
- An operator runbook covering SQLite WAL handling, persistence, resources,
  failure modes, and the supplied LXC procedure.
- OCI label/build-argument support and local hardened runtime smoke coverage.
- An explicit handoff to
  `~/git/homelab/ansible-workspace/playbooks/proxmox/create_reefproof_lxc.yml`
  and `deploy_reefproof.yml`.

Out of scope:

- Executing the first GHCR publication, immutable digest verification, or LXC
  acceptance procedure. The tag-triggered workflow and runbooks are included,
  but publication and infrastructure mutation require separate human approval.
- Live HYDROS access, credentials, network transports, remediation, or public
  ingress.
- The disabled-by-default service-runtime retention policy; the one-shot SRE
  commands do not activate it.

## Risks

- SQLite WAL files can be missed by an unsafe filesystem copy.
- A synthetic smoke scenario must not be mistaken for a live-system result.
- Repeated runs must not duplicate canonical snapshots or opening/recovery
  transitions.
- A read-only OCI filesystem requires all durable writes to the mounted data
  directory.
- Confusing the LXC host data path with the container data path can create an
  apparently empty replacement deployment.

## Homelab LXC handoff

The authoritative infrastructure implementation is in
`~/git/homelab/ansible-workspace/playbooks/proxmox/`.

Before applying it, update `templates/reefproof-run.service.j2` so the Podman
invocation explicitly passes these supported settings into the container:

```text
--env=REEFPROOF_DATA_DIRECTORY=/var/lib/reefproof
--env=REEFPROOF_TIMEZONE={{ reefproof_timezone_effective }}
```

The current template declares both only in systemd's host-process environment.
The image's matching data-directory default makes persistence work, but a
non-default runbook timezone does not currently reach ReefProof. Do not replace
this bounded forwarding with an environment file or general environment
passthrough.

1. Run `create_reefproof_lxc.yml` with vault-backed Proxmox credentials,
   `reefproof_ct_ip`, `reefproof_ct_gateway`, and a root password of at least
   16 characters. Its defaults create unprivileged CT 218 with nesting and
   keyctl enabled.
2. Add the resulting address to the homelab inventory group `[reefproof]`.
3. Obtain the successful tag workflow's deployment receipt and copy its
   `ghcr.io/bobbravo2/reefproof@sha256:...` reference. A tag alone is not a
   deployment input.
4. Run `deploy_reefproof.yml` with:

   ```yaml
   reefproof_image: ghcr.io/bobbravo2/reefproof@sha256:REPLACE_WITH_DIGEST
   reefproof_command: "infra-smoke --format json"
   reefproof_network_mode: none
   reefproof_require_digest: true
   ```

   The playbook's default timezone, timer, memory, and CPU limits may be
   overridden explicitly. Do not add HYDROS, Home Assistant, MQTT, or operator
   credentials to this v0.1 scheduled smoke deployment.

The LXC directory `/var/lib/reefproof/data` is mounted at
`/var/lib/reefproof` inside the container. The image sets
`REEFPROOF_DATA_DIRECTORY=/var/lib/reefproof`, so the database is stored on the
LXC host at `/var/lib/reefproof/data/reefproof.sqlite3`. Back up the database
through `reefproof storage backup`; do not copy a live SQLite main file without
its WAL sidecars.

## Evaluation

- Targeted CLI and storage tests including two executions against one empty
  data directory.
- Hardened Podman invocation with read-only root, no network, no capabilities,
  and a writable `/var/lib/reefproof` volume.
- `make check`.

## Completion Criteria

- `infra-smoke` exits zero and emits deterministic JSON after first and repeat
  execution.
- It writes only beneath the selected data directory, labels all input as
  synthetic, and verifies distinct snapshots, evaluation results, and finding
  transitions.
- Storage operations and limitations are documented precisely.
- OCI metadata and local workflow tests reflect the non-root, read-only
  runtime contract.
- The homelab deployment is supplied an immutable image digest, runs
  `infra-smoke --format json` with networking disabled, and reports a
  successful one-shot systemd result.
- A rendered unit with a non-default timezone explicitly passes that timezone
  and `REEFPROOF_DATA_DIRECTORY=/var/lib/reefproof` into the container.

## Open Questions

- What non-default retention period and off-host backup policy are acceptable
  for evidence in the first production deployment?
- What measured CPU, memory, runtime, and disk-growth limits should replace the
  conservative runbook defaults after target-LXC acceptance?
