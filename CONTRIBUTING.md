# Contributing

Start every session with the workflow in `AGENTS.md`. Repository state and
accepted architecture decisions take precedence over remembered conversation
context.

`uv` is configured in `pyproject.toml` to use the gitignored project-local
`.cache/uv` directory. Run `uv ...` directly from the repository; do not
override it with a user-home cache path, which may be inaccessible to sandboxed
or parallel agents.

Keep changes small, preserve the v0.1 read-only boundary, and do not add product
code before an approved task calls for it. Add a plan only when the planning
threshold in `AGENTS.md` applies.

## API checklist

Before adding or changing an HTTP operation:

- place every non-presentation API under `/v1`; only Workbench HTML, static
  assets, and favicons may be unversioned;
- use resource-oriented paths, safe/idempotent `GET`, and explicit create or
  action `POST`; update ADR 0008's exhaustive resource/method matrix rather than
  adding speculative CRUD;
- require `operatorSession` authentication and applicable authorization for
  every mutation except session establishment;
- declare bounded route/audit metadata and verify durable outcomes for success,
  denial, invalid input, and internal failure;
- use route templates, methods, status classes, and bounded outcomes in logs and
  metrics—never raw URLs, request bodies, cookies, secrets, authenticator codes,
  private identifiers, or unrestricted paths; and
- regenerate the Workbench TypeScript contract from `/v1/openapi.json` and run
  the executable API inventory before handoff.

The browser Workbench bundle is generated from
`src/reefproof/api/web/typescript/workbench.ts`. Do not edit
`src/reefproof/api/web/static/workbench.js` directly. The generated bundle is a
tracked release input; rebuild it with `npm run build` and commit it with its
TypeScript source so clean release staging cannot omit the browser application.

For version bumps, tags, GHCR publication, or corrections to an existing GitHub
Release, follow [the release and release-notes runbook](docs/releasing.md). Every
tag requires `docs/releases/vX.Y.Z.md`; generated technical evidence supplements
human notes and never replaces the summary, upgrade guidance, or changelog.

Use the one-writer and optional read-only reviewer workflow in
`docs/player-coach-loop.md`. The superseded coach protocol is historical only
and must not be loaded as current agent guidance.

Before handing off work that changes project capability, the current gate, or
the assigned next task:

1. Run the relevant commands registered in `.agent/evals.yaml`; small compatible
   repairs instead use focused tests plus the exact interface acceptance in
   `AGENTS.md`.
2. Update `.agent/current-state.md` and `.agent/next-task.md`.
3. Record accepted decisions or unresolved questions in the appropriate file.
4. Report what was tested, what was not tested, residual risks, and the exact
   next task.

For the current repository phase, run:

```bash
./scripts/check-baseline.sh
```

The installed pre-commit hook and canonical `make check` gate run the pytest
contract in `tests/integration/test_api.py`. It compares every ADR
0008 matrix column with the FastAPI route inventory and generated OpenAPI.
Run it alone with `make test/api-contract` while changing an API contract.

The Python suite uses eight bounded workers with xdist work stealing. This is
the measured repository default; increasing the worker count oversubscribes the
supported local development machine and makes the suite slower.

The pre-commit hook also parses every Mermaid code fence in staged Markdown
files. Run the same check directly for selected files with
`npm run mermaid:check -- README.md docs/example.md`.
