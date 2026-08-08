# ADR 0003: Trustworthy State Engine and Project Information Architecture

- Status: Accepted
- Date: 2026-07-25
- Decision owner: Customer 0
- Scope: ReefProof project state, intelligent-interface boundary, and v0.1
  information architecture

## Context

ReefProof must preserve a durable, evidence-backed understanding of the
v0.1 reference project while helping its operator recover project context quickly. Sessions,
interviews, source material, and generated explanations are useful inputs and
historical evidence, but none can safely substitute for canonical domain state.

The initial product supports one durable reef project
without prematurely imposing multi-project administration. Interview sessions
explain how understanding evolved and may propose facts, but the project
remains the durable home and Customer 0 remains the v0.1 acceptance authority.

HYDROS remains runtime authority. This decision does not authorize device
control, automatic remediation, credentials, MQTT publication, or mutation of
controller configuration.

## Decision

### ReefProof is a state engine, not a chat application

Canonical state consists only of typed, durable domain data: equipment, inputs,
outputs, operating modes, relationships, dependencies, observations, evidence,
decisions, assumptions, questions, findings, invariant results, commissioning
state, and structured recommended actions.

System maps, findings, unknowns, risk posture, commissioning status, and the
recommended next action are deterministic projections of that state. Prose,
chat transcripts, generated summaries, and unaccepted LLM conclusions are
non-canonical.

### The project is the durable home

The v0.1 project identity is `Mock Collective`. Sessions and structured
interview records belong to that project. Stable project identifiers preserve
a future multi-system path, but v0.1 does not implement speculative
multi-project administration.

### Information architecture is purpose-based

```text
ReefProof
└── Mock Collective
    ├── Overview
    ├── System Map
    ├── Assurance
    │   ├── Findings
    │   ├── Unknowns
    │   ├── Rules
    │   ├── Decisions
    │   └── Assumptions
    ├── Evidence
    └── Sessions
        ├── Continue interview
        ├── Candidate review queue
        └── History
```

Conversation is an interaction mode, not a primary information area.

### Overview is the orientation surface

Overview presents, in order:

1. the single structured recommended next action;
2. current commissioning or operational posture;
3. highest-consequence risks;
4. important unknowns;
5. recent accepted decisions;
6. a compact system map; and
7. a contextual `Continue interview` action.

Selecting the recommendation opens a stable action-detail surface before any
resolution workflow. It exposes priority, determinacy, affected objects, reason
codes, supporting findings and evidence, unresolved assumptions, blockers,
expected state transition, and human-judgment requirement.

### System Map is the canonical visual projection

One map uses selectable layers for physical layout, water flow, power, control,
dependencies, evidence status, and findings. Layer selection changes
presentation only. Typed equipment and relationship data remain authoritative.

Whether full equipment detail is primarily a stable page, a map inspector, or
both remains an explicit open product decision.

### Sessions are attributable audit records

Every session records stable identity, initiating user, purpose, scope,
absolute timestamps, typed questions and source answers, transcript and
attachment references, candidate facts, proposer provenance, validation
results, the acceptance authority's accept or reject decisions, and resulting domain-event
identifiers.

The transcript is evidence of what was said. It is never replayed as the
authoritative project database.

### Customer 0 is the sole v0.1 fact-acceptance authority

Agents and deterministic parsers may propose candidate facts. Only Customer 0 may
accept or reject them in v0.1. Acceptance records the candidate, deciding user,
timestamp, validation outcome, rationale, and resulting domain event.

An accepted fact becomes canonical only through an append-only domain event.
Rejecting a candidate preserves its history without changing project state.
Agents may not approve their own proposals.

### LLM capability is bounded

An LLM may parse source material into candidate facts, select and phrase
questions derived from structured unknowns, and narrate deterministic results.
It may not act as the database, evaluator, dependency engine, safety authority,
risk-ranking authority, equipment-state source, or implicit owner of truth.

Without an LLM ReefProof must still load the project, render maps and
relationships, evaluate invariants, preserve `PASS`/`FAIL`/`UNKNOWN`, expose
missing or stale evidence, list questions, select a recommended action, render
Overview, and explain results through reason codes and templates.

### Recommended actions are structured and deterministic

A recommended action contains a stable identity and type, affected equipment
or subsystem, blockers, reason codes, supporting findings and evidence,
unresolved assumptions, expected state transition, determinacy, and whether
human judgment is required.

Ranking order is safety, catastrophic-failure prevention, commissioning
blockers, high-impact unknowns, dependency prerequisites, evidence freshness,
operational reliability, then convenience or aesthetics. An LLM cannot
silently override this ordering.

### Epistemic categories remain explicit

ReefProof distinguishes fact, deterministic inference, assumption, unknown,
candidate, and finding. Consequential assertions retain source identity,
timestamp, scope, and freshness when relevant. Absence of evidence is never
converted into evidence of absence.

## Canonical flow

```text
human statement or source material
        ↓
typed candidate facts
        ↓
schema and domain validation
        ↓
Customer 0 accepts or rejects
        ↓
append-only domain event
        ↓
canonical project state
        ↓
rules, rankings, maps, findings, and Overview
```

## Consequences

- Domain state and deterministic projections remain independent from web
  templates and LLM adapters.
- Candidate and acceptance history is append-only and attributable.
- Generated summaries are disposable and reproducible.
- Purpose-specific actions replace generic chat entry points.
- UI completion cannot establish domain correctness by itself.
- Physical-model proposals use the same candidate-validation-acceptance-event
  boundary and cannot silently alter the model.

## Required evidence

- Typed models make invalid epistemic and authority states difficult to
  represent.
- Deterministic tests cover provenance, missing evidence, event replay,
  acceptance-authority-only approval, and no-LLM operation.
- Structural tests prove new interfaces cannot reach HYDROS, MQTT, or
  controller mutation paths.
- Navigation and API contracts distinguish canonical, derived, candidate, and
  presentational data.

## Open decision

- Choose whether equipment detail is a stable page, a map-side inspector, or
  both before implementing that public interaction.
