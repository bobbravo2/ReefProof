# ReefProof system API quick reference

This reference describes the current v0.1 system API. ADR 0008 contains the
exhaustive route and method contract; `tests/integration/test_api.py`
verifies every matrix column against the application and generated OpenAPI.

## Canonical endpoints

- `GET /v1/system/status` returns the current runtime, readiness, monitoring,
  configuration, evaluation, and active-finding summary.
- `GET /v1/system/health/live` returns `{"status": "alive"}` while the service
  can answer requests.
- `GET /v1/system/health/ready` returns the evaluated readiness report and uses
  HTTP `503` when assurance is unready.
- `GET /v1/system/metrics` returns bounded Prometheus metrics.
- `GET /v1/findings` returns active findings.
- `GET /v1/findings/{invariant_id}` returns one active finding or `404`.

All JSON system and finding routes are versioned. Workbench HTML remains under
`/workbench`; it does not define a separate system-status API.

## Status response

`GET /v1/system/status` is assembled from `RuntimeState`, evaluated readiness,
the current Workbench runtime projection, and persisted active-finding counts.
Its principal fields are:

- `version`, `project_id`, `runtime`, and `uptime_seconds`;
- `operating_mode`, `hydros_connection`, and `mqtt_connection`;
- configuration and evaluation timestamps and hashes;
- `alert_delivery_state`, `monitoring_confidence`, `readiness`, and `reasons`;
  and
- `active_findings`, keyed by severity and finding state.

Readiness is `ready`, `degraded`, or `unready`. Monitoring confidence is
`healthy`, `degraded`, `lost`, or `unknown`. Missing, stale, or unevaluated
configuration, an unloaded policy, unwritable durable storage, or an
unrecoverable transport failure contributes a bounded readiness reason.

## Runtime and authentication seams

The application factory is `create_app()` in `src/reefproof/api/app.py`. Its
relevant dependency names include `runtime_state`, `database`,
`hosted_operations`, `bootstrap_secret`, and `acceptance_principal_id`.

`HostedOperations` exposes the fixed-purpose methods `diagnostics()`,
`backup()`, `claim_backup()`, and `restart()`. Hosted operations require a
valid operator session and the exact `X-ReefProof-Operation: desktop` intent
header; that header is not an authenticator.

The canonical initial-session environment variable is
`REEFPROOF_BOOTSTRAP_SECRET`. Runtime and deployment configuration are
documented in `README.md` and `docs/operations.md`.

## Evidence boundary

The health and status APIs report ReefProof service state. They do not prove a
live HYDROS connection, validate physical equipment, establish release
acceptance, or grant ReefProof equipment-control authority. HYDROS remains
runtime authority.
