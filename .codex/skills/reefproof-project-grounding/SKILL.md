---
name: reefproof-project-grounding
description: Deterministically ground ReefProof from bounded repository files, deriving identity, safety boundary, current gate, architecture, implementation status, next task, and git state without LLM or network access.
---

# ReefProof project grounding

Start with compact, steering-aware context:

```bash
python .codex/skills/reefproof-project-grounding/scripts/extract.py --repo . --format llm
```

Hints:

- Need architecture or capability inventories? Rerun with detail:

```bash
python .codex/skills/reefproof-project-grounding/scripts/extract.py --repo . --format llm --detail
```

- Need stable fields for a machine consumer? Use JSON:

```bash
python .codex/skills/reefproof-project-grounding/scripts/extract.py --repo . --format json
```

The extractor must:

- read only the bounded repository files listed in the script;
- use no LLM calls and no network access;
- create no files by default;
- validate required context and exit nonzero on invalid input;
- report contradictions instead of guessing;
- produce byte-identical JSON for the same repository state.

The `llm` format keeps the same authoritative project facts while removing
repeated provenance wrappers. Its `R`, `V`, and `W` records summarize the
repository-owned task routes, interface validation, and dirty-tree contract.
Its `N`, `C`, and `B` records preserve the next-task outcome, completion
criteria, and boundary without Markdown formatting.

Read the compact output, then the assigned task and only task-relevant code.
Do not reread repository status documents unless the task or a contradiction
requires them.
