# ADR 0004: Identity-Bound Zero-Trust Sessions

- Status: Accepted identity/session model; reachability superseded by ADR 0007
- Date: 2026-07-25
- Decision owner: Customer 0
- Scope: Local authentication, human acceptance authority, and project identity

## Context

The initial v0.1 state engine conflated a customer display name, project
identity, actor role, and acceptance authority. Its browser session proved
possession of one environment secret but carried no authenticated principal.
The candidate-review route then fabricated the deciding actor from project
configuration.

The Homelab Wellness service provides a tested application-session pattern:
successful authentication produces a signed, expiring, `HttpOnly`,
`SameSite=strict` cookie that protected routes verify independently. Its full
deployment also uses Cloudflare Access and application TOTP, but those remote
exposure and dependency choices are outside ReefProof v0.1.

## Decision

ReefProof v0.1 remains single-project. `local-managed` mode is loopback-only;
ADR 0007 permits `remote-hosted` access to one explicit private-LAN ReefProof
origin. The configured or generated bootstrap secret establishes the first
session and TOTP enrollment; subsequent authentication uses TOTP. Successful
authentication creates an opaque server-side session bound to one configured
principal and sets a signed, expiring browser cookie.

Every protected project read and human decision revalidates the cookie and
resolves its server-side principal. Candidate review derives its actor only from
that authenticated session. Request bodies cannot provide identity, role,
validation, event identity, or event sequence.

Authorization identity and presentation are separate:

- `project_id` is a stable technical identifier.
- `project_display_name` is configurable presentation data.
- `principal_id` is the stable authorization and provenance identity.
- `principal_display_name` is presentation only.
- `acceptance_authority_principal_id` selects the sole v0.1 human authority.
- `human_acceptance_authority` is a capability role, not a person.

New installations default to project ID `primary-reef-system`. Existing
person-attributed evidence remains immutable legacy history and is never
silently relabeled.

Logout clears the cookie and revokes the process-local session. Missing,
expired, malformed, tampered, or unknown sessions receive `401`. An
authenticated principal that is not the configured project authority receives
`403`.

## Consequences

- Display labels cannot grant authority.
- Browser JavaScript cannot read or persist the session credential.
- Service restart invalidates all browser sessions.
- Public remote access, Cloudflare Access, and multi-user identity remain
  separately gated future decisions.
- HYDROS remains runtime authority; this decision adds no controller, MQTT, or
  remediation capability.

## Required evidence

- Signed-cookie verification, expiry, revocation, tamper, and cookie-attribute
  tests.
- Principal mismatch fails closed before any decision is written.
- Append-only replay retains exact historic and new principal attribution.
- Structural tests reject person-specific executable identity and any
  controller mutation capability.
