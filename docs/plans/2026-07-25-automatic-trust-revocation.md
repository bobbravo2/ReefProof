# Automatic trust-revocation vertical slice

Status: Implemented WIP, preserved and deferred from the current v0.1
proof-of-trust gate.

## Outcome

The acceptance authority can revoke reliance on one canonical evidence item or subsystem using both
configured authority factors, observe deterministic downstream
`UNKNOWN / REVOKED` propagation, and restore trust only with complete fresh
accepted evidence plus another replay-protected phone TOTP.

## Scope and non-goals

Scope includes the append-only trust stream, schema 0006, pure dependency
closure, TOTP enrollment/reset, authority-bound APIs, typed contracts, Evidence
Workbench controls, and focused safety/evaluation coverage. Canonical history,
project-wide revocation, web reset, multi-user administration, live HYDROS,
MQTT, and remediation are excluded.

## Risks

- A dependency cycle or derivation failure must fail closed.
- TOTP material must never enter SQLite, backups, responses after enrollment,
  or logs.
- Restoration must not accept stale, partial, rejected, or mismatched facts.
- The retained experimental Database explorer must remain unstaged.

## Evaluation

Run focused trust, persistence, session, project API, CLI, browser, generated
contract, and safety checks, then uninterrupted `make check`.

## Completion criteria

Trust history is immutable and replayable; scopes are canonical; propagation is
deterministic; both mutations require fresh TOTP verification; restoration is
fresh and complete; APIs reject unauthenticated, one-factor, or unauthorized
callers; the Workbench is keyboard-readable; backup/restore includes trust but
excludes TOTP; the safety boundary passes.

## Open questions

None for this accepted v0.1 slice.
