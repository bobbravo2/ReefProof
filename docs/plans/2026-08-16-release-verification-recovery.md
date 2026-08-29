# Release Verification Recovery

## Outcome

Recover the valuable release-verification contracts from the archived pre-sync
history without restoring obsolete release metadata, incremental development
schemas, or technical-only release notes.

## Scope

- Require the distribution verifier to compare its manifest with an
  independently supplied release identity and source revision.
- Restore fast negative-path tests for bundle identity, OCI execution identity,
  and default command validation.
- Add structured `hydros-check` output and compare the same offline evaluation
  result across source, standalone, and OCI runtimes.
- Keep real artifact parity under `build/verify`; ordinary pytest uses supplied
  result documents and never builds artifacts or starts a container.
- Move the Proxmox backup and restore procedure into Homelab-owned agent
  guidance after satisfying that repository's coordination contract.
- Remove the obsolete divergent branch refs after recovered work is preserved.

## Boundaries

No live HYDROS transport, controller mutation, MQTT publication, automatic
remediation, release publication, deployment, or infrastructure mutation is
authorized. Existing concurrent Workbench and v0.1.2 changes remain untouched.

## Verification

- Focused verifier, CLI, Make-interface, and safety tests.
- `bash -n` for changed shell-adjacent build behavior where applicable.
- One final `make check` after focused tests, if the concurrent working tree is
  stable enough to provide uncontaminated evidence.
- Homelab's repository-owned skill checks after registration; otherwise report
  the coordination blocker without writing into its dirty checkout.
