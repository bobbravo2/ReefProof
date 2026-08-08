# Phase 2 Typed Reliability Graph

Status: Completed.

## Outcome

Build a deterministic typed graph from canonical configuration snapshots and
explain explicit dependency cycles and correlated redundant devices without
live HYDROS access or invariant-policy claims.

## Scope

In scope:

- Typed observed and authored graph nodes.
- Typed annotation-backed edges with evidence references.
- Deterministic graph construction and JSON rendering.
- Directed dependency-cycle detection.
- Detection and plain-language explanation of redundant devices sharing an
  explicitly annotated power domain.
- A synthetic unsafe-correlated-returns fixture.
- A credential-free CLI graph inspection command.

Out of scope:

- General invariant results or severities.
- Claims that a detected graph shape is unsafe without a versioned invariant.
- HYDROS transport, network access, credentials, polling, MQTT, remediation,
  alerting, persistence, or a graph dependency.

## Risks

- Graph analysis could accidentally infer missing physical relationships.
- Annotation-backed edges could be mistaken for vendor observations.
- A graph-shape warning could be mistaken for an evaluated safety finding.

Every node and edge therefore retains provenance and evidence identity. The CLI
describes graph facts only; Phase 3 will own `PASS`, `FAIL`, and `UNKNOWN`
policy results.

## Evaluation

- Unit tests cover deterministic construction, provenance, correlated failure
  domains, dependency cycles, missing relationships, and stable rendering.
- CLI tests demonstrate a plain-language correlated-redundancy explanation.
- `make check` remains the combined integration gate.

## Completion criteria

- Graph nodes distinguish `OBSERVED` and `AUTHORED`.
- Graph edges cite the source annotation.
- Input ordering does not affect rendered graph JSON.
- A redundant return pair sharing a power domain is explained with names and
  evidence.
- A missing power relationship is not guessed.
- Dependency cycles are returned deterministically.
- The user-facing demonstration uses only fixtures.
