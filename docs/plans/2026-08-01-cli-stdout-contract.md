# CLI stdout contract

## Outcome

Make `./reefproof status` useful as a shell health check, keep its human output
aligned with the running ReefProof service, and render plain help whenever
stdout is not attached to a terminal.

## Contract

- `status` exits `0` only when the configured ReefProof service responds with a
  valid current status document.
- An unreachable or invalid service prints a concise `FAIL` result and exits
  `1`.
- A running service reports its observed operating mode, assurance readiness,
  and monitoring confidence. A stopped service reports the configured mode and
  does not present it as observed runtime state.
- Help retains rich terminal rendering for attached terminals and automatically
  uses Click's plain formatter for redirected stdout, `TERM=dumb`, or
  `NO_COLOR`.
- Human-readable output comes first. A machine-readable output option is not
  part of this change.

## History boundary

Command history remains unchanged in this change. Its sidecar log is under the
application data directory but is not included by the SQLite-only
`storage backup` and `storage restore` commands. Moving history into backed-up
persistence or stopping collection requires a separate explicit decision.

## Verification

- Focused CLI status tests cover running, unreachable, and invalid-service
  responses, including exit status and observed/configured mode wording.
- Launcher acceptance covers redirected plain help and attached-TTY rich help.
- Run `bash -n reefproof`, the focused registered CLI evaluation, the exact
  launcher interfaces, and one final repository gate.
