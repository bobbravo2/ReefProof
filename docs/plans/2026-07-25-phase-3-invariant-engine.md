# Phase 3 Three-State Invariant Engine

Status: Completed.

## Outcome

Evaluate typed reliability graphs with explicit Python rules that return
versioned `PASS`, `FAIL`, or `UNKNOWN` evidence, beginning with
`RP-CIRC-001`, `RP-CIRC-002`, `RP-CIRC-003`, `RP-FALLBACK-001`, `RP-FLOW-001`, `RP-FLOW-002`,
`RP-HEAT-001`, `RP-HEAT-002`, `RP-LOGIC-001`, `RP-MODE-001`, `RP-WATER-001`, and
`RP-WATER-002`, plus the three independent `RP-MONITOR-*` health rules.

## Scope

In scope:

- Typed invariant result and severity models.
- Deterministic policy identity.
- A small explicit rule registry and evaluation engine.
- `RP-CIRC-001`: intended redundant returns sharing a power domain.
- `RP-CIRC-002`: every evaluated mode retains circulation or oxygenation.
- `RP-CIRC-003`: Low Power retains battery-approved circulation.
- `RP-FALLBACK-001`: critical unavailable-input behavior is known and assessed.
- `RP-FLOW-001`: active UV loads depend on adequate-flow permissives.
- `RP-FLOW-002`: active chillers depend on adequate-flow permissives.
- `RP-HEAT-001`: redundant heaters use independent typed failure domains.
- `RP-HEAT-002`: active heaters have independent safeguards.
- `RP-LOGIC-001`: explicit dependency relationships contain a cycle.
- `RP-MODE-001`: service modes have finite positive timeouts.
- `RP-WATER-001`: active ATO paths have bounded freshwater addition.
- `RP-WATER-002`: automated RODI fills have independent high-high cutoffs.
- `RP-MONITOR-001..003`: observation, evaluation, and alert-delivery confidence.
- `PASS`, `FAIL`, and `UNKNOWN` tests.
- Text and JSON `reefproof check --fixture ...` output with documented exit
  codes.
- Human-readable `reefproof explain <invariant-id>` output.

Out of scope:

- A policy DSL.
- Live HYDROS access, service endpoints, persistence, alert delivery, polling,
  MQTT, or remediation.
- Remaining v0.1 rule families until these verticals establish reusable
  evidence.

## Risks

- Missing relationships could be mistaken for safety.
- Graph-shape detection could be confused with policy evaluation.
- Exit codes could become inconsistent across rules.

The engine therefore treats missing required evidence as `UNKNOWN`, keeps rule
metadata versioned, and owns exit-code selection separately from graph analysis.

## Evaluation

- Every implemented rule has `PASS`, `FAIL`, and `UNKNOWN` tests.
- CLI tests cover text, JSON, explain output, and exit codes.
- `make check` remains the combined gate.

## Completion criteria

- The correlated-return fixture produces one critical `FAIL` with named
  entities, evidence, and a human action.
- An independent-power fixture produces `PASS`.
- Missing power-domain evidence produces `UNKNOWN`, never `PASS`.
- A dependency cycle produces `FAIL`; an acyclic graph produces `PASS` only
  when dependency-map completeness is explicitly authored, and otherwise
  produces `UNKNOWN`.
- An indefinite service-mode timeout produces `FAIL`; a positive timeout
  produces `PASS` only with explicit inventory-completeness evidence.
- A confirmed missing heater safeguard produces `FAIL`; missing confirmation
  produces `UNKNOWN`, never `PASS`.
- An active UV load without an adequate-flow dependency produces `FAIL` only
  when active-load and dependency-map completeness are explicit.
- Active chillers use the same explicit completeness and dependency evidence
  contract as UV loads.
- ATO safety requires a finite runtime, measurable flow or volume bound,
  high-water inhibit, and independent high stop.
- RODI safety distinguishes a confirmed missing high-high cutoff (`FAIL`) from
  missing evidence (`UNKNOWN`).
- Critical fallback behavior passes only when both the behavior and its safety
  assessment are explicit.
- Low Power can fail for missing circulation only when mode identity and
  membership completeness are explicit.
- Heater independence covers power domains, controllers, sole control sensors,
  and sole dependencies through typed graph edges.
- System-wide circulation fails only after operating modes, memberships, and
  approved functions are all explicitly complete.
- Policy and evaluation identities are present.
- JSON output contains the complete typed result.
- Text output is understandable without internal database knowledge.
