# Monitor Health Invariants

Status: Completed.

## Outcome

Evaluate ReefProof's own observation, policy-evaluation, and alert-delivery
confidence independently from the living-system reliability graph.

## Scope

In scope:

- A typed runtime-health context.
- `RP-MONITOR-001` configuration-observation staleness.
- `RP-MONITOR-002` policy-evaluation staleness.
- `RP-MONITOR-003` local alert-delivery health.
- Explicit `PASS`, `FAIL`, and `UNKNOWN` results.
- Honest support for an unknown configuration hash before first observation.

Out of scope:

- HTTP endpoints, SQLite persistence, scheduling, or live transport.
- Treating Home Assistant as the reporter for its own delivery failure.
- Claims about HYDROS safety from ReefProof-health failures.

## Risks

- Monitor failure could be mislabeled as controller unsafety.
- Startup without a configuration could fabricate evidence.
- Wall-clock comparisons could mix naive and timezone-aware timestamps.

Monitor results therefore use distinct summaries and operator actions, preserve
timezone-aware times, and permit the literal `UNKNOWN` when no configuration
hash exists.

## Evaluation

- Each monitor rule has `PASS`, `FAIL`, and `UNKNOWN` tests.
- Boundary-time tests use an injected evaluation timestamp.
- Graph invariant behavior remains unchanged.

## Completion criteria

- Stale observation and evaluation produce local critical failures.
- Unverified initial state produces `UNKNOWN`.
- Alert delivery failure is locally visible without invoking an alert adapter.
- No monitor result implies HYDROS itself is unsafe.
