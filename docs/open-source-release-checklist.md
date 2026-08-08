# Open-source release checklist

This checklist defines when ReefProof may be made public. It supplements the
product and artifact requirements in `docs/release-criteria.md`; it does not
replace target-LXC or packaged-desktop acceptance.

## Repository boundary

- The public repository uses `https://github.com/bobbravo2/ReefProof` and the
  matching `ghcr.io/bobbravo2/reefproof` package namespace.
- Product copy, fixtures, tests, documentation, and generated artifacts contain
  no private aquarium identity, private device identifier, personal filesystem
  path, local database, browser evidence, or captured configuration.
- Synthetic credential-shaped fixtures use conspicuous `SEED-*` values and
  documentation-only IP address ranges.
- `LICENSE`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, and
  `CODE_OF_CONDUCT.md` are present and current.

## Secret and history audit

Before selecting the candidate commit, run both scans from a clean checkout:

```bash
gitleaks dir --no-banner --redact .
gitleaks git --no-banner --redact .
```

Also inspect all reachable object names for accidentally committed databases,
environment files other than `.env.example`, keys, captures, and private export
formats. A scanner finding is investigated; it is never dismissed solely
because another scanner is green. If real private material ever entered a
reachable commit, remove it from every public ref before publication and rotate
the affected credential. Deleting it only from the current tree is insufficient.

Git author identity and the authorized `bobbravo2` publication namespace are
normal repository metadata. Product-facing references to a private person's
aquarium or acceptance decisions are not permitted.

## Candidate evidence

- The Python suite passes within its 15-second local wall-clock service budget.
- `make check` passes after the final source or documentation change.
- `make build` passes from the exact clean candidate commit.
- Standalone, OCI, and packaged desktop artifacts pass their repository-owned
  verification commands and contain no local/private material.
- Supported local browser and attached-terminal paths have current behavioral
  evidence.
- Target-LXC and both packaged desktop modes have current acceptance evidence,
  or the release remains a candidate and is not tagged or published.
- The candidate is reviewed for dependency licenses, vulnerability findings,
  generated-contract parity, and immutable workflow action pins.

Publishing, pushing a rewritten history, creating `v0.1.0`, or uploading any
artifact remains an explicit release action. Local readiness checks do not
perform those actions.
