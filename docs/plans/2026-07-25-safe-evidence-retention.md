# Safe Evidence Retention

Status: Completed in the service runtime; the one-shot CLI does not activate it.

## Outcome

Allow an operator to bound durable evaluation-detail growth without deleting
the distinct normalized configurations, evaluation summaries, finding
transitions, active findings, or alert outcomes needed to explain ReefProof's
history.

Retention is disabled by default. Enabling it is an explicit local storage
choice; it never affects HYDROS or any living-system controller.

## Scope

In scope:

- An optional evaluation-detail retention period in the main configuration.
- Durable result-state summaries on every evaluation run.
- Migration and backfill of existing evaluation summaries.
- Transactional pruning of only old `invariant_results` rows.
- A startup retention pass when the operator explicitly configures a period.
- A report stating the cutoff and number of detail rows removed.

Out of scope:

- Deleting normalized snapshots, finding transitions, active findings, alert
  attempts, or evaluation-run summaries.
- Time-based deletion enabled by default.
- Background compaction, `VACUUM`, backup deletion, or off-host retention.
- Any network or controller interaction.

## Risks

- Pruning could remove evidence still required for an active finding.
- Timestamp or timezone mistakes could prune newer evidence.
- A migration could summarize existing evaluations incorrectly.
- Cascades could delete transitions or summaries unintentionally.

The implementation therefore uses timezone-aware cutoffs, stores summaries
before permitting pruning, preserves transition and active-finding result
documents, and tests exact table counts before and after restart.

## Evaluation

- Migration and summary-backfill tests.
- Disabled-by-default configuration test.
- Boundary test proving rows at the cutoff are retained.
- Pruning test proving only older invariant-result detail is removed.
- Restart test proving summaries, snapshots, transitions, findings, and alert
  attempts remain.
- Full application and safety gates.

## Completion Criteria

- Existing databases migrate without losing evidence.
- Every evaluation run has PASS, FAIL, UNKNOWN, and total result counts.
- No detail is pruned when retention is unset.
- Explicit retention deletes only eligible `invariant_results`.
- All protected evidence remains queryable after pruning and restart.
- The runtime reports retention outcome without claiming a backup exists.
