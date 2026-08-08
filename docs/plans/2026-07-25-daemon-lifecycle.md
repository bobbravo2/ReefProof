# Local Daemon Lifecycle and CLI Documentation

Status: Implemented WIP, preserved and deferred from the current v0.1
proof-of-trust gate.

## Outcome

Provide a small, local process lifecycle interface for the loopback workbench:
`reefproof daemon start`, `reefproof daemon stop`, and `reefproof daemon status`.
The existing foreground `reefproof serve` command remains the primary development
entry point.

## Scope and non-goals

- Record one detached `serve --no-open --no-reload` child in a configurable PID
  file, defaulting beneath `REEFPROOF_DATA_DIRECTORY`.
- Observe PID state with portable process-existence checks, detect stale and
  malformed PID files, and request graceful SIGTERM shutdown with a bounded
  wait.
- Send detached output to a configurable local log file.
- Keep all commands loopback-only and read-only with respect to living-system
  configuration.
- Document every public CLI command and test its help output.
- Do not add a process manager dependency, force-kill a timed-out process, or
  change the foreground server's API behavior.

## Risks

- A PID file cannot prove process identity after PID reuse; stop is limited to
  the explicitly recorded local PID and stale files are never signaled.
- A daemon that exits immediately after start can leave a stale PID file; the
  next `status` or `start` operation reports or cleans it deterministically.
- Detached logs are local operator evidence and are not durable ReefProof
  configuration evidence.

## Evaluation

- Unit tests cover stopped, running, stale, and malformed PID observations;
  detached start; duplicate start rejection; graceful stop; and CLI status.
- A table-driven CLI test covers help for every top-level and nested command.
- `make check` remains the integration gate.

## Completion criteria

- `reefproof daemon start|stop|status` is discoverable from `reefproof --help`.
- Default and explicit PID/log paths are reported to the operator.
- `daemon stop` is idempotent for an absent or stale PID file.
- Existing `reefproof serve` foreground and development reload behavior remains
  covered.

## Open questions

None for this local lifecycle slice. A production service manager remains the
deployment authority outside this CLI.
