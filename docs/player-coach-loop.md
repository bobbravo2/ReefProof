# One Writer and Optional Reviewer Loop

Use one Codex main session as the only writer. Do not create separate builder,
test-runner, supervisor, coordinator, or routing agents.

## Writer loop

1. Run project grounding:

   ```console
   python .codex/skills/reefproof-project-grounding/scripts/extract.py --repo . --format json
   ```

2. Classify the task using `AGENTS.md`.
3. Implement one narrow coherent slice and run focused tests.
4. For a small compatible repair, exercise the exact affected interface; that
   is the final gate and no reviewer is required.
5. For a material checkpoint, invoke `reefproof_reviewer` with the goal,
   acceptance criteria, exact commit or diff, changed paths, focused test
   evidence, and accepted exceptions.
6. For a material change, run one final deterministic repository gate, present
   the evidence, and ask the human for acceptance.

## Boundaries

- The main session is the only writer. The optional reviewer is read-only and
  advisory.
- Do not invoke the reviewer for a read-only review or small compatible repair.
- The reviewer returns `NO_ACTION` or one `MATERIAL_ISSUE` with evidence,
  impact, the smallest correction, and one verification.
- Missing required evidence is a `MATERIAL_ISSUE`, never an inferred `PASS`.
- The reviewer never approves, edits, commits, pushes, publishes, or deploys.
- Do not present a default, unanswered question, or timeout as human approval.
- Missing token and dollar values remain `UNKNOWN`.
- A human stop applies immediately.

Token telemetry remains a manual optional command:

```console
./scripts/agent-usage.sh summary
```

It is not part of startup, Stop, SessionEnd, tests, or release gates. UI tooling
is enabled only during explicit UI work.
