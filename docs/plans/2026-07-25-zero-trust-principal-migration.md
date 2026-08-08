# Zero-Trust Principal Migration

## Outcome

Replace person-specific project and acceptance authority with a configured,
identity-bound principal. Reuse the proven Wellness application-session pattern:
an authentication factor establishes a short-lived signed `HttpOnly`,
`SameSite=strict` cookie that every protected request revalidates.

## Scope

- Keep ReefProof loopback-only.
- Keep one v0.1 project and one configured human acceptance authority.
- Use the existing environment-only operator secret as the authentication
  factor; add no dependency.
- Bind process-local sessions to a stable configured principal.
- Derive decision attribution only from the authenticated session.
- Default the project to `primary-reef-system` with configurable display data.
- Preserve already stored person-specific evidence as immutable legacy history.
- Remove person-specific names, roles, routes, defaults, and errors from
  executable code and generated contracts.

## Non-goals

- Cloudflare Access, public routing, remote deployment, TOTP enrollment, or QR
  generation.
- Multi-user or multi-project administration.
- Changing HYDROS authority, adding controller mutation, MQTT publication, or
  automatic remediation.
- Rewriting historical decision attribution.

## Risks

- A signed cookie without server-side expiry and principal binding could
  authenticate possession without establishing authority.
- A migration could silently rewrite immutable historical evidence.
- Compatibility aliases could preserve person-specific identifiers in the
  executable surface.
- Browser code could accidentally retain the old reusable session-header model.

## Evaluation

- Session signature, expiry, tamper, logout, cookie-attribute, and principal
  binding tests.
- `401` for missing, invalid, and expired sessions; `403` for an authenticated
  non-authority principal.
- Candidate acceptance/rejection tests proving actor attribution comes only from
  the authenticated session.
- Restart, replay, migration, backup, and restore tests preserving exact legacy
  attribution.
- Structural zero-hit scan for person-specific executable identifiers.
- Generated OpenAPI/TypeScript parity, browser tests, and `make check`.

## Completion criteria

- Display names cannot grant authority.
- The decision body cannot supply identity, role, validation, event ID, or
  sequence.
- One valid authority acceptance creates exactly one atomic event attributed to
  the session principal; rejection creates none.
- Unknown, expired, tampered, or mismatched sessions fail closed.
- Existing historical evidence is readable without relabeling.
- No person-specific identifier remains in executable defaults, roles, routes,
  migrations, contracts, or errors.
- ReefProof remains loopback-only and structurally unable to control HYDROS.

## Result

Completed on 2026-07-25. Signed, expiring, process-local browser sessions bind
the configured acceptance principal to protected requests. Candidate review
derives attribution from that session and rejects a principal that does not
match the durable project authority. Fresh installations use
`primary-reef-system`; a runtime with one existing project adopts its recorded
technical identity without inserting, relabeling, or rewriting evidence.
Generated browser contracts and runtime validators consume the resulting API.
