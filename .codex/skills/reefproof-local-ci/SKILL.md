---
name: reefproof-local-ci
description: Run ReefProof local build, quality, and Nektos act CI validations through deterministic one-shot repository commands. Use for local pre-push checks, reproducing GitHub Actions checks or delivery jobs, building the standalone binary or complete bundle, and reporting exact local CI evidence without publishing, releasing, deploying, or invoking agent benchmarks.
---

# ReefProof Local CI

Run every task through `scripts/run.sh` from this skill. Do not reconstruct CI
commands manually when a task below covers the request.

## Workflow

1. Run ReefProof project grounding.
2. Inspect `git status --short`. Preserve unrelated changes.
3. Select the smallest task that exercises the requested boundary.
4. Preview it with `scripts/run.sh --print TASK` when command scope matters.
5. Invoke it once with `scripts/run.sh TASK`.
6. Report the exact task, exit status, result, and boundary exercised.

## Tasks

- `local-check`: run the canonical local quality gate.
- `local-binary`: build and verify the standalone CLI artifact.
- `local-bundle`: build and verify the complete local distribution bundle.
- `act-checks`: reproduce `.github/workflows/checks.yml` job `check`.
- `act-delivery-binary-linux`: reproduce the Linux delivery binary job only.
- `act-delivery-container`: reproduce the delivery OCI job through the
  repository's Podman-aware launcher.
- `list`: display the task catalog without running a gate.

Use `local-check` for ordinary pre-push validation. Use `act-checks` only when
the GitHub Actions container boundary matters. Build tasks require a clean Git
tree because the repository build contract rejects dirty packaging.

## Determinism and safety

- Use only checked-in Make targets, workflow files, and scripts.
- Keep the event, workflow, job, Linux matrix value, and `--pull=false`
  explicit for `act`.
- Route every `act` task through `scripts/run-act.sh`. It prefers
  `podman-machine-default`, starts that existing machine when stopped, and
  falls back to a running Docker daemon only when the Podman machine is
  unavailable. Set `REEFPROOF_PODMAN_MACHINE` to select another existing
  machine explicitly.
- Do not pass arbitrary extra arguments through the task runner.
- Do not run `.github/workflows/release.yml`; it contains publication behavior.
- Do not run `make agent/benchmark` or other authenticated agent evaluation.
- Do not push, tag, publish, deploy, connect to HYDROS, or add secrets.
- Treat missing `act`, Podman, cached runner images, or clean-tree state as a
  failed prerequisite, not permission to alter the CI contract.
- Run each requested gate once. Do not retry a failing gate before identifying
  the concrete failure.

The `act` results are local emulation evidence, not hosted GitHub Actions or
release evidence. Mark unsupported macOS matrix coverage and any skipped
container boundary as `NOT TESTED`.
