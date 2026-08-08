# Continuous Delivery Plan

Status: Implemented locally; hosted artifact jobs and the local Actions
container job remain unverified at this boundary.

## Outcome

Provide GitHub Actions gates, reproducible local commands, and smoke-tested
artifacts for the ReefProof CLI as a standalone executable and an OCI image.

## Scope

- Preserve the existing lint, type, test, and doctor gate.
- Build standalone Linux and macOS CLI executables.
- Build an unprivileged OCI image and smoke-test it with a read-only root filesystem.
- Keep the Linux jobs compatible with local `act` execution.

## Non-goals

- Publishing releases or images.
- Adding credentials, network transport, or any living-system mutation path.
- Cross-compilation or code signing.
- Automatic deployment.

## Risks

- PyInstaller artifacts are specific to their build operating system and architecture.
- Container builds require access to pinned base images.
- Local `act` behavior is representative of Linux Actions jobs, not hosted macOS.

## Evaluation

- `make check`
- `make binary`
- `podman build --tag reefproof:local .`
- `podman run --rm --read-only --tmpfs /tmp reefproof:local version`
- `podman run --rm --read-only --tmpfs /tmp reefproof:local infra-smoke --format json`
- `./scripts/run-local-delivery.sh`

## Completion criteria

- The existing quality gate remains green.
- The binary starts without the repository environment and passes `version` and `doctor`.
- The OCI image runs as a non-root user with a read-only root filesystem.
- GitHub Actions uploads Linux and macOS binary artifacts.
- The Linux container job passes under the local Actions runner.

## Open questions

- Which additional architectures are required for the first release?
