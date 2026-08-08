# ADR 0001: Product Architecture and Safety Boundary

- Status: Proposed
- Date: 2026-07-25
- Decision owners: ReefProof maintainers
- Scope: Product direction from offline modeling through v0.1

## Context

ReefProof is configuration assurance for living systems. Its first intended
source is CoralVue HYDROS, but its assurance model should remain useful beyond
one controller vendor.

The product should observe controller configuration, preserve evidence,
construct a typed system-wide reliability model, evaluate authored safety
invariants, and notify a human when the observed system is unsafe or cannot be
assessed confidently.

The permanent invariant remains:

> ReefProof may observe, model, challenge, and alert on a living system. It may
> not silently take control of one.

This ADR condenses a broader product brief into durable architectural choices.
It does not authorize implementation of every component, dependency, endpoint,
or phase described below.

## Evidence status

This is a proposed umbrella ADR, not the current capability record. Its
implementation snapshot from the initial drafting pass was removed because it
became stale as fixture, persistence, service, and alerting slices landed.
Current evidence belongs in `README.md` and `.agent/current-state.md`; accepted
decisions are indexed in `docs/architecture-decisions.md`. Descriptions of
future transport and live-system behavior in this ADR remain `PROPOSED`.

## Decision drivers

1. Immediate user-visible safety value.
2. Structural separation from controller mutation capability.
3. Truthful `PASS`, `FAIL`, and `UNKNOWN` results.
4. Evidence-backed, human-readable findings and operator actions.
5. Fixture-first development without live credentials or hardware.
6. Observable failure and loss of monitoring confidence.
7. A vendor-neutral reliability model.
8. Local-first operation on macOS and an OCI-compatible Linux runtime.
9. Narrow, complete vertical slices rather than speculative scaffolding.

## Proposed decision

### 1. Authority and assurance model

HYDROS remains runtime authority. ReefProof is an independent assurance plane,
not a desired-state replica or control plane.

ReefProof evaluates observed configuration against separately authored safety
invariants and physical-system annotations. It records safe and unsafe
observations for audit, but v0.1 does not page merely because configuration
changed.

Git may preserve exported evidence. Git is not runtime authority, and ReefProof
does not automatically restore, commit, or push controller configuration.

### 2. Structural read-only boundary

The v0.1 runtime may:

- Load fixtures and sanitized snapshots.
- Authenticate and perform narrowly defined read-only discovery and retrieval
  only after a transport ADR is accepted.
- Normalize observations.
- Store evidence and evaluation history.
- Evaluate invariants.
- Produce reports, health, status, findings, metrics, and notifications.

The v0.1 runtime may not:

- Change outputs, modes, schedules, firmware, membership, or configuration.
- Upload configuration or register or remove devices.
- Expose general-purpose HTTP mutation or MQTT publication.
- Automatically remediate a finding.
- Treat advice or a finding as executable authority.

Mutation capability must be absent from the runtime dependency graph, not
hidden by naming or convention. Safety tests must prove the negative boundary.

### 3. MQTT status-listening exception is rejected for v0.1

The source brief proposed publishing one exact empty request to initiate status
streaming. That conflicts with the currently accepted rule that v0.1 may not
publish to MQTT.

ADR 0002 accepts a precise boundary: ReefProof v0.1 sends no MQTT `PUBLISH`
packet, including an empty status-listening request. A future MQTT subscriber
may send connection and subscription control packets only after a separate
transport decision and structural proof.

If response streaming requires application publication, v0.1 cannot use that
stream and must rely on an accepted read-only retrieval mechanism.

### 4. Observed facts, annotations, and derivations stay separate

The canonical model distinguishes:

- `OBSERVED`: vendor-supplied facts with source paths and capture evidence.
- `AUTHORED`: human-maintained annotations with owner and review metadata.
- `DERIVED`: relationships produced by explicit rules with evidence.
- `CONFIRMED`: facts explicitly verified by a human.
- `ASSUMED`: declared assumptions that must never be promoted silently.
- `UNKNOWN`: missing or indeterminate information.

Vendor extensions remain preserved without being assigned invented semantics.
Private physical-system annotations and device identifiers are not committed
without an explicit sanitization policy.

### 5. Typed reliability model

Use typed entities and typed relationships rather than a graph made only of
free-form strings.

The model should eventually represent controllers, ports, power outlets,
electrical and control failure domains, sensors, outputs, devices, functions,
modes, schedules, dependencies, combiners, flow permissives, safeguards,
reliability tiers, and commissioning evidence.

The graph is derived from observed facts plus separately loaded annotations.
Transport-specific structures do not leak into invariant evaluation.

### 6. Three-state invariant results

Every invariant returns exactly `PASS`, `FAIL`, or `UNKNOWN`.

Each result includes its invariant identity and version, severity, summary,
explanation, affected entities, evidence, missing evidence, recommended human
action, timestamps, input hashes, policy hash, and evaluation run identity.

Missing evidence never evaluates as `PASS`. Each invariant defines how an
`UNKNOWN` result affects health and alerting.

Typed Python rules precede any general policy language. A policy DSL is
considered only after implemented rules demonstrate repeated structure.

### 7. Initial reliability scope

Candidate initial rule families are:

- Correlated circulation and heating failure domains.
- No surviving circulation or oxygenation path.
- Low-power modes without approved circulation.
- Flow-dependent UV and chilling loads without proven flow.
- Unbounded ATO and insufficiently protected automated water addition.
- Indefinite service modes.
- Dependency or combiner cycles.
- Unknown critical fallback behavior.
- Stale configuration observation, stale evaluation, and unhealthy alert
  delivery.

The exact first-release set remains subject to fixture evidence and per-rule
`PASS`, `FAIL`, and `UNKNOWN` tests.

### 8. Observability is part of correctness

Every major component reports health, connection state where applicable, last
success, latest evaluated input identity, policy identity, current findings,
delivery state, degradation reason, and whether the assurance result is
trustworthy.

A silent monitor is failed or `UNKNOWN`, never healthy by omission.

Metrics use bounded labels. Secrets, signed URLs, full vendor payloads, private
identifiers, and exception text are not metric labels or default log fields.

Proposed service endpoints are `/health/live`, `/health/ready`, `/status`,
`/findings`, `/findings/{id}`, and `/metrics`. They are deferred until a
fixture-backed service slice provides observable value.

### 9. Alerting remains an adapter

Invariant evaluation produces findings independently of notification
technology.

For v0.1, critical new `FAIL` results may produce one P0 notification;
persistent findings are deduplicated, and a return to `PASS` produces one
recovery transition. Critical `UNKNOWN` notification policy is configurable.

Home Assistant and console delivery sit behind narrow adapters. Home Assistant
failure remains visible locally and does not depend on Home Assistant to report
itself.

### 10. Runtime progression

Implementation proceeds in complete fixture-first slices:

1. Offline observed models, annotations, stable IDs, normalization, hashes, and
   snapshot export.
2. Typed reliability graph and evidence-backed traversal.
3. Three-state invariant engine and human-readable reports.
4. Fixture-backed local health, status, persistence, and metrics.
5. Console and Home Assistant alert adapters with deduplication and recovery.
6. Read-only one-shot HYDROS retrieval, only after a transport ADR and
   structural safety tests.
7. Conservative continuous polling with explicit vendor-safe limits.
8. Passive MQTT observation research without application publication.
9. Hybrid observation only if captured evidence justifies it without
   superseding ADR 0002.

No phase is current merely because it appears in this sequence.

### 11. Technology posture

Continue the accepted Python 3.13, uv, Typer, Pydantic v2, structlog, Pytest,
Ruff, and Pyright foundation.

The following are candidates, not approved dependencies: httpx, anyio, FastAPI,
Prometheus client, SQLite/Alembic, Jinja2, YAML tooling, and NetworkX. Add each
only in the slice that demonstrates immediate value, with evaluation coverage
and the required plan.

Prefer a small explicit typed graph until graph operations justify NetworkX.
Do not require PostgreSQL, Redis, Kafka, Kubernetes, Grafana, Loki, or an
OpenTelemetry collector for v0.1.

### 12. Upstream HYDROS research

`Bitf1ip/pyhydros` version `0.4.1` may be evaluated as protocol research input,
not imported wholesale into the daemon and not yet added as a dependency.

Proposed provenance:

```text
Project: Bitf1ip/pyhydros
Version: 0.4.1
License: MIT
Purpose: protocol research for a future narrow read-only adapter
```

The release documents authentication, REST/S3 retrieval, AWS IoT MQTT,
wildcard subscriptions, MQTT publication, and mode mutation.
Consequently, its complete runtime surface is incompatible with ReefProof's
read-only boundary.

Before deriving or copying code:

- Review the pinned source and transitive dependencies.
- Record exact commit and file-level provenance.
- Preserve required MIT license and attribution.
- Isolate only behavior required by an accepted transport ADR.
- Prove mutation and general-purpose publication are structurally unreachable.
- Test secret redaction and failure preservation.

### 13. Security and deployment posture

Secrets come from environment variables or mounted secret files, never
committed YAML. Credentials, tokens, cookies, temporary cloud credentials,
signed URLs, private identifiers, and unsanitized captures must not enter logs,
snapshots, fixtures, or Git.

The first deployment remains local-first. A future OCI image should run as a
non-root user, use persistent writable storage, accept external secrets, expose
an explicit health check, and terminate gracefully. Kubernetes is not required.

## Revised or redacted from the source brief

- Personal names and person-specific reef topology were generalized to operator
  roles and anonymized example systems.
- Concrete live identifiers, account details, credentials, and private physical
  annotations were excluded.
- The large target directory tree was not adopted as required scaffolding;
  paths should appear only with the vertical slice that uses them.
- Technology choices beyond the current stack were changed from mandates to
  candidates requiring demonstrated value.
- The proposed MQTT publication exception was rejected for v0.1 by accepted
  ADR 0002.
- `pyhydros` was changed from a mandated implementation source to a pinned
  research candidate pending license, dependency, protocol, and safety review.
- Claims about live configuration-change signals and safe polling frequency
  remain `UNKNOWN`.
- Product examples were retained as candidate requirements, not claims about
  current HYDROS semantics or current ReefProof capability.

## Consequences

### Positive

- Product value stays centered on reliability compilation rather than
  controller transport.
- Invariants remain testable with fixtures and independent of credentials.
- Safety and monitoring uncertainty are explicit.
- Later vendor support can reuse the canonical model and evaluation engine.
- Alert explanations can cite evidence without exposing vendor internals.

### Costs and limitations

- Human annotations require ownership and periodic review.
- Three-state evaluation is more demanding than optimistic Boolean checks.
- Structural read-only proof requires dedicated negative tests.
- Live integration is intentionally delayed until offline semantics are useful.
- Reverse-engineered behavior may change and cannot be treated as vendor
  support.

## Acceptance prerequisites

This ADR may become accepted only after maintainers explicitly resolve:

1. Whether this umbrella ADR should be split into narrower decisions.
2. The exact v0.1 invariant set.
3. The policy for sanitized observed fixtures and private annotations.
4. A separate read-only transport ADR with structural negative tests.
5. Vendor-safe polling behavior supported by evidence.
6. Home Assistant delivery behavior and secret handling.

Resolved separately:

- ADR 0002 rejects MQTT application publication for v0.1.

Acceptance of this ADR would not itself authorize live-system testing.

## References

- Current repository policy: `AGENTS.md`
- Accepted decisions: `docs/architecture-decisions.md`
- Accepted MQTT boundary: `docs/adr/0002-no-mqtt-publication-in-v0-1.md`
- Current unknowns: `docs/open-questions.md`
- Initial offline slice:
  `docs/plans/2026-07-25-phase-1-offline-hydros-fixtures.md`
- pyhydros 0.4.1 release:
  <https://pypi.org/project/pyhydros/0.4.1/>
- pyhydros source: <https://github.com/Bitf1ip/pyhydros>
