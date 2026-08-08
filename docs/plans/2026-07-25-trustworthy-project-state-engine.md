# Trustworthy Project State Engine

Status: In progress.

## Outcome

Implement ADR 0003 as a deterministic, durable project-state engine for the
Reliable Reef V4. ReefProof must preserve what is known, unknown, accepted, and
recommended without relying on conversation history or an LLM.

## Scope

- Typed project, actor, interview, candidate, validation, decision, event, and
  canonical-fact contracts.
- Acceptance-authority-only candidate approval and deterministic event replay.
- Typed information architecture and structured recommended actions.
- SQLite persistence for sessions, candidates, decisions, and domain events.
- Read-only project projections plus explicit candidate-review endpoints.
- Overview and action-detail projections derived from canonical state.
- Tests for no-LLM operation, provenance, authority, missing evidence,
  determinism, and the read-only controller boundary.

## Non-goals

- Live HYDROS/AWS access, credentials, MQTT, device control, or automatic
  remediation.
- Generic chat as a product surface or transcript replay as state recovery.
- Multi-project administration.
- An equipment-detail route before Customer 0 chooses page, inspector, or both.
- LLM prompt correctness as a release gate.

## Canonical-state classification

- **Canonical:** accepted facts and append-only domain events.
- **Derived:** project brief, system-map projection, findings, unknowns,
  commissioning posture, and recommended action.
- **Candidate:** parser, agent, or interview proposals awaiting acceptance-authority review.
- **Presentational:** navigation layout, selected map layers, prose summaries,
  and generated explanations.

## Risks

- A write endpoint could bypass the configured acceptance authority.
- Event persistence could allow gaps, rewrites, or nondeterministic replay.
- UI summaries could be mistaken for canonical state.
- Private physical annotations could be persisted before their policy is
  accepted.
- A recommendation narrator could accidentally influence deterministic ranking.

## Evaluation

- `uv run pytest tests/unit/test_project_state.py tests/unit/test_recommendations.py tests/unit/test_information_architecture.py`
- `uv run pytest tests/safety/test_project_state_boundary.py`
- Focused persistence and API integration tests as those slices are added.
- `make check`

## Completion criteria

- Acceptance-authority approval is the only path from candidate fact to canonical event.
- Sessions preserve initiator, source answers, candidates, decisions, and
  resulting event identities.
- Replaying the same complete event sequence produces identical project state.
- Recommended-action ranking follows ADR 0003 without LLM input.
- The exact sitemap and Overview order serialize deterministically.
- Durable storage and read projections survive restart and backup/restore.
- New interfaces have no path to HYDROS, MQTT, or controller mutation.

## Implementation tracking

- VERIFIED: Typed canonical state, acceptance-authority-only decisions, append-only replay,
  recommendations, and information architecture (`c03962a`).
- VERIFIED: Schema version 4 persistence, deterministic Project Brief,
  attributable physical proposals, and verified backup/restore (`9a06f26`).
- VERIFIED: Authenticated project reads and explicit candidate review
  (`6c6dfd4`).
  Browser requests contain only the operator's decision and rationale. Schema/domain
  validation is server-side and deterministic; unregistered domains fail
  closed instead of accepting a caller's validity claim.
- VERIFIED: Overview and Sessions authenticate through a process-local session,
  consume the generated project contracts, preserve UNKNOWN and provenance,
  and submit only the operator's decision plus rationale for candidate review.

## Open question

- Whether equipment detail is a stable page, a map inspector, or both.
