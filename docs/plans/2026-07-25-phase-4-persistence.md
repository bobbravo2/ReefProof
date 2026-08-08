# Phase 4 Durable Evaluation History

Status: Completed.

## Outcome

Persist distinct normalized snapshots, evaluation results, active findings, and
finding transitions in local SQLite without weakening evidence or alert
deduplication semantics.

## Scope

In scope:

- SQLite WAL mode and explicit schema migrations.
- Distinct snapshots keyed by canonical snapshot hash.
- Durable evaluation runs and complete typed results.
- One active finding per invariant with first/last seen and occurrence count.
- One opening transition and one recovery transition.
- Durable alert attempts and adapter-specific success timestamps; only
  successful delivery advances retry state for that adapter.
- Restart preservation and transaction rollback on failure.
- Alembic integration before Phase 4 is marked complete.

Out of scope for the original slice:

- HTTP routes, alert delivery, or live transport.

Retention pruning is implemented as a later safety-reviewed slice in
`docs/plans/2026-07-25-safe-evidence-retention.md`.

Out of scope:

- Storing credentials, signed URLs, or raw private vendor payloads.

## Risks

- Partial writes could separate an evaluation from its findings.
- Repeated evaluations could duplicate P0 candidates.
- Restart could lose recovery state.
- Schema evolution could become implicit.

Each evaluation is therefore one immediate transaction, schema versions are
explicit, and transition behavior is covered across database restart.

## Evaluation

- Migration and WAL tests.
- Duplicate-snapshot test.
- New, repeated, and recovered finding tests.
- Restart preservation test.
- Full application and safety gate.

## Completion criteria

- Repeating one violation increments its occurrence count without another open
  transition.
- Returning to `PASS` creates one recovery and removes the active finding.
- Repeating `PASS` creates no additional recovery.
- Every stored result can be reconstructed as its typed model.
- Failed alert delivery remains eligible for retry after restart.
- One successful adapter does not suppress retry for another failed adapter.
- Alembic migration state is tested.
