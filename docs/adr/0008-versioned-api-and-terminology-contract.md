# ADR 0008: Versioned API and terminology contract

- Status: Accepted
- Date: 2026-08-08
- Decision owner: Customer 0
- Scope: HTTP resource and method surface, authorization tiers, API mutation
  auditing, bounded observability, fresh-v0.1 database recognition, and public
  terminology
- Refines: ADR 0004, ADR 0005, ADR 0006, and ADR 0007

## Decision

All ReefProof JSON, OpenAPI, documentation, health, status, findings, metrics,
database, project, Workbench, and operations APIs use `/v1`. Only HTML
Workbench pages, static assets, and favicons may be unversioned. Paths are
resource-oriented: safe/idempotent reads use `GET`; creation and explicit
actions use `POST`. The route matrix below is the exhaustive v0.1 API contract.
The executable inventory compares the application routes and OpenAPI methods to
this exact set; no wildcard or “existing routes” shorthand grants authority.

`operatorSession` is the OpenAPI security scheme for protected operations.
Bootstrap secrets and six-digit authenticator codes are write-only fields used
only to establish an operator session. The `X-ReefProof-Operation: desktop`
header is a required, non-secret intent signal for hosted operations. It is not
an authenticator and grants no authority without a valid operator session.

Authorization tiers mean:

- `public`: no existing session is required.
- `operatorSession`: a valid identity-bound operator session is required.
- `acceptanceAuthority`: an operator session whose principal is the configured
  project acceptance authority is required; trust mutations additionally
  require a fresh authenticator code.
- `hostedDesktopOperation`: a valid operator session and the exact desktop
  operation intent signal are both required.

The OpenAPI document is served at `/v1/openapi.json`; `/v1/docs` renders that
same document locally without CDN assets or interactive request controls.
FastAPI's default `/openapi.json`, `/docs`, and `/redoc` are disabled.

## Exhaustive resource and method matrix

“Audit” below means exactly one generic immutable `api_mutation_audit` row per
HTTP attempt. Domain records remain independently authoritative and do not
replace or duplicate that generic row.

| Path | Method | Authentication | Authorization | Persistence/audit | Success status |
| --- | --- | --- | --- | --- | --- |
| `/v1/openapi.json` | `GET` | public | public | none | `200` |
| `/v1/openapi.json` | `HEAD` | public | public | none | `200` |
| `/v1/docs` | `GET` | public | public | none | `200` |
| `/v1/system/status` | `GET` | public | public | none | `200` |
| `/v1/system/health/live` | `GET` | public | public | none | `200` |
| `/v1/system/health/ready` | `GET` | public | public | none | `200` |
| `/v1/system/metrics` | `GET` | public | public | none | `200` |
| `/v1/findings` | `GET` | public | public | none | `200` |
| `/v1/findings/{invariant_id}` | `GET` | public | public | none | `200` |
| `/v1/workbench/actions` | `GET` | public | public | none | `200` |
| `/v1/workbench/electrical-posture` | `GET` | public | public | none | `200` |
| `/v1/workbench/policy-template` | `GET` | public | public | none | `200` |
| `/v1/workbench/policy-preview` | `POST` | public | public | non-persisting evaluation; no audit | `200` |
| `/v1/workbench/policy-revisions` | `POST` | operatorSession | operatorSession | audit; immutable policy revision on success | `201` |
| `/v1/workbench/policy-revisions/latest` | `GET` | public | public | none | `200` |
| `/v1/workbench/invariant-catalog` | `GET` | public | public | none | `200` |
| `/v1/workbench/physical-twin` | `GET` | public | public | none | `200` |
| `/v1/workbench/auth-method` | `GET` | public | public | none | `200` |
| `/v1/workbench/operator-sessions` | `POST` | public | session establishment | audit; operator session on success | `201` |
| `/v1/workbench/operator-sessions/current/revocations` | `POST` | public | idempotent current-session revocation | audit; revoke valid current session if present | `204` |
| `/v1/workbench/totp` | `GET` | operatorSession | operatorSession | none | `200` |
| `/v1/workbench/totp/enrollment` | `POST` | operatorSession | operatorSession | audit; pending authenticator state on success | `201` |
| `/v1/workbench/totp/enrollment/confirm` | `POST` | operatorSession | operatorSession | audit; confirmed authenticator state on success | `204` |
| `/v1/projects/{project_id}` | `GET` | operatorSession | operatorSession | none | `200` |
| `/v1/projects/{project_id}/state` | `GET` | operatorSession | operatorSession | none | `200` |
| `/v1/projects/{project_id}/brief` | `GET` | operatorSession | operatorSession | none | `200` |
| `/v1/projects/{project_id}/authored-sources` | `GET` | operatorSession | operatorSession | none | `200` |
| `/v1/projects/{project_id}/authored-sources/google-sheets/status` | `GET` | operatorSession | operatorSession | none | `200` |
| `/v1/projects/{project_id}/authored-sources/google-sheets/sync` | `POST` | operatorSession | acceptanceAuthority | audit; immutable source snapshot, import batch, and review candidates on changed valid content | `201` |
| `/v1/projects/{project_id}/imports` | `GET` | operatorSession | operatorSession | none | `200` |
| `/v1/projects/{project_id}/imports/{import_batch_id}` | `GET` | operatorSession | operatorSession | none | `200` |
| `/v1/projects/{project_id}/imports/{import_batch_id}/review` | `POST` | operatorSession | acceptanceAuthority | audit; immutable candidate decisions, canonical events, and external identity bindings on acceptance | `201` |
| `/v1/projects/{project_id}/labels` | `GET` | operatorSession | operatorSession | none | `200` |
| `/v1/projects/{project_id}/labels.csv` | `GET` | operatorSession | operatorSession | none | `200` |
| `/v1/projects/{project_id}/reconciliation` | `GET` | operatorSession | operatorSession | none | `200` |
| `/v1/projects/{project_id}/reconciliation/bindings` | `POST` | operatorSession | acceptanceAuthority | audit; immutable explicit observed-to-canonical identity binding | `201` |
| `/v1/projects/{project_id}/commissioning` | `GET` | operatorSession | operatorSession | none | `200` |
| `/v1/projects/{project_id}/commissioning/verifications` | `POST` | operatorSession | acceptanceAuthority | audit; immutable commissioning verification on success | `201` |
| `/v1/projects/{project_id}/commissioning/label-verifications` | `POST` | operatorSession | acceptanceAuthority | audit; immutable physical label verification on success | `201` |
| `/v1/projects/{project_id}/commissioning/failure-mode-dispositions` | `POST` | operatorSession | acceptanceAuthority | audit; immutable failure-mode disposition on success | `201` |
| `/v1/projects/{project_id}/sessions` | `GET` | operatorSession | operatorSession | none | `200` |
| `/v1/projects/{project_id}/sessions/{interview_session_id}` | `GET` | operatorSession | operatorSession | none | `200` |
| `/v1/projects/{project_id}/candidates` | `GET` | operatorSession | operatorSession | none | `200` |
| `/v1/projects/{project_id}/trust` | `GET` | operatorSession | operatorSession | none | `200` |
| `/v1/projects/{project_id}/trust/revocations` | `POST` | operatorSession | acceptanceAuthority | audit; immutable trust event on success | `201` |
| `/v1/projects/{project_id}/trust/restorations` | `POST` | operatorSession | acceptanceAuthority | audit; immutable trust event on success | `201` |
| `/v1/projects/{project_id}/candidates/{candidate_fact_id}/review` | `POST` | operatorSession | acceptanceAuthority | audit; decision/domain event on success | `201` |
| `/v1/database/schema` | `GET` | operatorSession | operatorSession | query-only; none | `200` |
| `/v1/database/tables/{table_name}` | `GET` | operatorSession | operatorSession | query-only; none | `200` |
| `/v1/operations/diagnostics` | `GET` | operatorSession | hostedDesktopOperation | none | `200` |
| `/v1/operations/backups` | `POST` | operatorSession | hostedDesktopOperation | audit; staged backup on success | `201` |
| `/v1/operations/backups/{backup_id}/download` | `POST` | operatorSession | hostedDesktopOperation | audit; one-time claim on success | `200` |
| `/v1/operations/restart` | `POST` | operatorSession | hostedDesktopOperation | audit; supervisor request on success | `202` |

All other methods are intentionally absent. Retired routes have no aliases.
`/v1/database/schema` and `/v1/database/tables/{table_name}` remain query-only;
backup creation and download authority exists solely under the bounded
operations API, refining rather than contradicting ADR 0005.

## Mutation audit and request correlation

The mutation methods are `POST`, `PUT`, `PATCH`, and `DELETE`. ReefProof v0.1
declares no `PUT`, `PATCH`, or `DELETE` route, but attempts using those methods
are still mutation attempts. Exactly one generic audit row is written for:

- successful, denied, invalid, and failed mutation attempts;
- operator-session establishment, including invalid credentials;
- idempotent current-session revocation, including absent or invalid sessions;
- framework-generated `404`, `405`, `422`, and `500` mutation responses; and
- unmatched mutation paths, recorded with the bounded route name `unmatched`.

`POST /v1/workbench/policy-preview` is the sole exception: it evaluates a body
without persistence and receives no mutation-audit row. Reads, including hosted
diagnostics, receive no mutation-audit row. Domain events, policy revisions,
operator-session records, authenticator state, backups, and supervisor actions
remain authoritative; `api_mutation_audit` records only the API attempt and its
outcome, never request content.

Every response, including framework-generated `404`, `405`, `422`, and `500`
responses, receives a server-generated `X-ReefProof-Request-ID`. Structured
request logs and metrics use only the bounded route template, method, request
ID, status class, mutation outcome, and bounded duration. They exclude cookies,
request bodies, secrets, authenticator codes, private identifiers, raw URLs,
and unrestricted paths.

## Opaque hosted backup identifiers

`backup_id` is a canonical UUIDv4 resource identifier. It is not a filename,
path, or storage locator. The server keeps the staged filename private and maps
the public ID to it in bounded process-local state. A successful download claim
atomically consumes the mapping before transfer, so concurrent or replayed
claims cannot succeed. The response uses the generic download filename
`reefproof-backup.sqlite3`; successful transfer cleanup deletes the claimed
staging file.

Staged backups expire after the configured bounded retention window. Malformed
or non-v4 IDs return `422`. Unknown, expired, and already-claimed IDs return
`404`. Service restart invalidates all process-local backup IDs; orphaned staged
files remain private and are removed by bounded cleanup.

## Fresh-v0.1 database recognition

Before Alembic or application startup may write, ReefProof inspects an existing
database read-only. It accepts only:

1. a nonexistent or empty path that can receive the single fresh-install
   schema; or
2. schema version `1`, Alembic revision `0001`, with exactly the v0.1 table set
   defined by the release migration.

Any other existing file fails startup immediately with an incompatible-schema
error and recovery instruction. ReefProof must not modify, migrate, rename,
delete, partially initialize, or open an incompatible database for application
service. The operator preserves or moves the old file aside and starts with a
new database path; normalized source exports remain the rebuild boundary.

## Identity terminology

- `principal_id` identifies the authenticated identity bound to an operator
  session and used for authorization.
- `actor_id` identifies the human, agent, or parser attributed in provenance and
  domain records; an authenticated principal may be represented as an actor
  when it performs an attributable domain decision.
- `session_id` identifies an operator session or, when explicitly qualified by
  the model/route, an interview session. Policy revisions use
  `authoring_operator_session_id`.

## Consequences

The v0.1 fresh schema uses `configuration_snapshots`,
`return_flow_policy_revisions`, and `api_mutation_audit`. Public timestamps use
`captured_at`; provenance references use `*_actor_id`; authenticated identities
remain principals. The CLI uses `database`, and the bootstrap environment
contract is `REEFPROOF_BOOTSTRAP_SECRET`. Existing incompatible databases are
preserved byte-for-byte and rejected before application startup.
