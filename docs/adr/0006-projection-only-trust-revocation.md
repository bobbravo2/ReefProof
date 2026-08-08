# ADR 0006: Projection-only trust revocation

- Status: Accepted
- Date: 2026-07-25
- Decision owner: Customer 0
- Release classification: DEFERRED IMPLEMENTED WIP

## Decision

ReefProof records acceptance-authority-approved evidence- or subsystem-scoped trust events in
an append-only stream independent of canonical project events. Active
revocations force affected projections and their transitive dependants to an
effective `UNKNOWN / REVOKED` state while retaining the raw evaluated state and
immutable historical values.

Both revocation and restoration require the configured authority's signed
session plus a fresh, non-replayed six-digit phone TOTP. This symmetric factor
policy prevents possession of the operator factor alone from persistently
denying assurance. Restoration additionally requires an accepted
post-revocation replacement for every captured root subject/attribute. Each
trust event records when its TOTP was verified, never the secret or code.
TOTP state is a mode-`0600` file outside SQLite and its backups. Reset rotates
the secret, increments an authentication generation, and invalidates existing
sessions.

Projection dependency cycles fail closed. HYDROS remains runtime authority;
trust actions cannot mutate controllers, canonical facts, decisions, evidence,
or prior evaluations.

## Consequences

The API gains authority-bound trust endpoints and authenticated TOTP enrollment.
`pyotp` and `qrcode[pil]` are bounded runtime dependencies. Customer 0 explicitly
accepted server-rendered PNG enrollment over an SVG-only or manual-key flow:
easy, familiar phone scanning is worth shipping Pillow in the Python and OCI
runtime. Exact dependency locking, SBOM generation, and the release
vulnerability gate mitigate the larger supply-chain and image footprint; they
do not erase it. Trust application occurs after deterministic evaluation and
before derived user-visible policy. Delivery failure cannot undo an accepted
revocation.

Requiring TOTP for urgent revocation is deliberate: the local CLI reset path is
the recovery mechanism when the phone factor is unavailable. ReefProof does not
trade durable authority evidence for a faster one-factor trust mutation.
Acceptance of this architecture does not place the implementation in the
current v0.1 proof-of-trust release path.
