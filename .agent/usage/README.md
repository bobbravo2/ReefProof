# Agent Usage Ledger

This directory records engineering outcomes alongside agent usage when that
usage is observable. It is an engineering calibration aid, not a productivity
contest or contributor ranking system.

`sessions.jsonl` contains one JSON object per session. It must never contain
prompts, responses, credentials, or conversation content. Missing telemetry is
stored as JSON `null` and displayed as `UNKNOWN`; it is never estimated as zero.
Dollar cost is recorded only when supplied by an authoritative harness or
billing source.

The installed Codex CLI documents usage in `codex exec --json`
`turn.completed` events. Interactive Codex transcripts also expose cumulative
`event_msg.payload.info.total_token_usage` counters. Explicitly supplied,
sanitized JSONL can be recorded manually through the adapters. Transcript
content is never copied. Because transcript formats are explicitly unstable,
unfamiliar or missing usage fields remain `UNKNOWN`.

This ledger is observational telemetry, not a coordination or locking system.
An `in_progress` result, elapsed time, session identity, and usage records
confer no path ownership and cannot prove that a writer is active or stale.
Coordinate concurrent work through direct exact-path handoffs until an
approved coordination system is available.

Use:

```bash
./scripts/agent-usage.sh start --task "Task name"
./scripts/agent-usage.sh record --session-id ID --codex-json events.jsonl --codex-version 0.145.0
./scripts/agent-usage.sh import --transcript transcript.jsonl --session-id ID
./scripts/agent-usage.sh finish --session-id ID
./scripts/agent-usage.sh summary
./scripts/agent-usage.sh validate
```

Use `--json` with any command for machine-readable output.

The idempotent `import` command can ingest an explicitly supplied transcript.
Dollar cost remains unknown unless an authoritative billing source supplies it;
subscription use is not converted to an invented API-equivalent price.
