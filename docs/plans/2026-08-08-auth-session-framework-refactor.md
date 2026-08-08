# Starlette/FastAPI Authentication and Session Refactor

## Outcome

Delegate cookie signing, parsing, expiry, and cookie attributes to Starlette
`SessionMiddleware`, and declare protected routes with FastAPI security
dependencies. Keep ReefProof's bootstrap-to-authenticator ceremony, durable
session revocation, authentication-generation invalidation, and configured
acceptance-authority checks.

## Boundaries

- Store only an opaque random session ID in the signed browser session.
- Keep principal, issue time, generation, and revocation authoritative in SQLite.
- Preserve all endpoint, payload, cookie-name, and status-code contracts.
- Generate a signing key per process, so restart invalidates existing cookies.
- Support loopback/private-LAN HTTP by default; HTTPS deployments explicitly set
  `api.session_https_only` or `REEFPROOF_SESSION_HTTPS_ONLY=true`.
- Do not add accounts, passwords, roles, OAuth, live HYDROS access, control
  authority, or general identity infrastructure.

## Implementation

1. Add explicit compatible Starlette and `itsdangerous` dependencies.
2. Reduce `OperatorSessions` to durable opaque-ID issue, resolve, list, and
   revoke behavior.
3. Add `SessionMiddleware` and centralized optional, required, and configured
   authority dependencies based on `APIKeyCookie`.
4. Convert project, Workbench, database, operation, and audit consumers to
   dependency-injected sessions.
5. Remove authentication-specific OpenAPI rewriting while retaining ReefProof
   audit metadata.
6. Update settings, documentation, CLI revocation coverage, and focused tests.

## Acceptance

Run the registered identity evaluation, directly affected API/CLI/browser tests,
generated-contract parity, a real loopback Workbench login/action/logout flow,
and one uninterrupted repository `local-check` gate. Existing cookies are
intentionally invalid after deployment and after every service restart.
