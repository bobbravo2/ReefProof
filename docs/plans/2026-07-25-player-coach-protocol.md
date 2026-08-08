# Native Player/Coach Loop

Status: Superseded by `docs/player-coach-loop.md`; retained as historical
evidence only. Do not use this plan as current agent guidance.

## Outcome

Use Codex's native subagent workflow:

- The main Codex session is the **engineer** and owns repository writes.
- One project-scoped **coach** subagent reviews evidence, cost, deviation, and
  wasted work.
- The engineer uses native subagent messaging, steering, waiting, and results.
- The human operator controls the main session from the available Codex
  surface.

No custom broker, database, supervisor, or cross-session protocol is required.

## Native loop

```text
Human operator
      |
      v
Main Codex engineer session
      |
      +---- native read-only coach subagent
      |
      v
Repository changes and evaluations
```

The engineer:

1. Reads the repository handoff and establishes a baseline.
2. Spawns one `reefproof_coach` subagent with the exact goal and acceptance
   criteria.
3. Implements one coherent slice.
4. Sends the coach a checkpoint only at a natural boundary.
5. Applies or rejects the coach's bounded advice using repository evidence.
6. Runs the final gate and asks the coach for one completion audit.
7. Reports results and closes the coach.

The coach:

- runs read-only;
- inspects current repository state;
- never edits files;
- returns at most one highest-leverage instruction per checkpoint;
- recommends the cheapest sufficient evaluation;
- treats unavailable cost as `UNKNOWN`; and
- does not request progress updates or periodic polling.

## Checkpoints

Ask the coach to review only when:

- a focused evaluation changes state;
- a coherent implementation slice is complete;
- the engineer is about to run a full gate;
- the full gate completes;
- safety or scope uncertainty appears; or
- the engineer claims completion.

Do not wake the coach for every tool call.

Use this checkpoint message:

```text
Checkpoint for <goal>.
Changed paths: <paths>.
Evaluation: <command and result>.
Next intended action: <action>.
Inspect the current repository state. Return only the highest-leverage
correctness, scope, safety, or efficiency correction. If none exists, say
NO_ACTION. Recommend the cheapest sufficient verification.
```

## Cost rules

- Use documented Codex usage events or an authoritative billing source.
- Missing token or dollar values remain `UNKNOWN`.
- A budget is not consumption.
- Track wall time, targeted evaluations, full gates, and rework separately.
- Never scrape transcripts or private Codex state.

Native subagents consume additional tokens. The coach must save more rework or
risk than it costs. One coach and checkpoint-based reviews are the default.

## Human operation

Start a new Codex session in this repository and give it:

```text
Act as the ReefProof engineer for <goal>. Follow AGENTS.md. Use the
project-scoped reefproof_coach native subagent. Keep the coach read-only.
Checkpoint only at coherent boundaries. Implement, test, and continue until the
acceptance criteria are proven. Run the registered final gate, request one
coach completion audit, update the handoff files, and commit only tested,
accepted work.
```

The operator can inspect or steer native subagents using the controls available
in the active Codex client. Web and iOS support depends on the operator's
account and current product surface; this repository adds no custom mobile
control plane.

## Safety

- Only the main engineer writes.
- The coach uses `sandbox_mode = "read-only"`.
- Advice cannot broaden user authority.
- The engineer preserves the ReefProof living-system boundary.
- A human stop applies immediately.
- Parallel write-heavy agents are not used.

## Evaluation

Structurally verify:

1. The project-scoped coach definition exists.
2. It has a unique name, description, and developer instructions.
3. Its sandbox is read-only.
4. Its instructions prohibit edits and scope expansion.
5. Its instructions require evidence, bounded advice, and truthful unknown
   usage.
6. Repository guidance defines checkpoint and completion-audit behavior.
7. The standard `make check` gate still passes.

## Completion criteria

- A new Codex main session can discover and spawn `reefproof_coach`.
- The coach is structurally read-only.
- A human can run the documented prompt without additional setup.
- One live trial completes checkpoint → advice or `NO_ACTION` → final audit.
- The engineer remains the only writer.
- Usage is measured or truthfully `UNKNOWN`.
- Tested accepted repository work is committed.

## Verification record

On 2026-07-25, `uv run pytest tests/unit/test_coach_agent.py` passed with 2
tests, Ruff checks passed, and Pyright reported zero errors. Two sequential
fresh `codex exec --sandbox read-only` trials each discovered and spawned the
project coach, completed one checkpoint and final audit, and made no repository
changes. The trials observed 32,894 and 31,999 tokens; dollar cost remains
`UNKNOWN`.

The repository-wide `make check` must pass on the exact committed snapshot.

## Non-goals

- Independent top-level agent sessions.
- Custom inter-agent messaging.
- SQLite, PostgreSQL, MCP, NATS, Redis, or Temporal coordination.
- Background daemons, heartbeats, or schedulers.
- A custom web or mobile UI.

## Sources

- [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Codex CLI commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli)
