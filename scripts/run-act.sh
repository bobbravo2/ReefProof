#!/usr/bin/env bash
set -euo pipefail

machine_name="${REEFPROOF_PODMAN_MACHINE:-podman-machine-default}"

if ! command -v act >/dev/null 2>&1; then
    printf 'FAIL: Nektos act is required\n' >&2
    exit 2
fi

run_with_podman() {
    podman machine inspect "$machine_name" >/dev/null 2>&1 || return 1
    machine_state="$(podman machine inspect "$machine_name" --format '{{.State}}')" || return 1
    if [[ "$machine_state" != "running" ]]; then
        printf 'START: Podman machine %s\n' "$machine_name"
        podman machine start "$machine_name" || return 1
    fi

    podman_socket="$(
        podman machine inspect "$machine_name" \
            --format '{{.ConnectionInfo.PodmanSocket.Path}}'
    )" || return 1
    machine_uid="$(podman machine ssh "$machine_name" id -u)" || return 1
    daemon_socket="/run/user/$machine_uid/podman/podman.sock"
    if [[ ! -S "$podman_socket" ]]; then
        printf 'WARN: Podman socket is unavailable: %s\n' "$podman_socket" >&2
        return 1
    fi

    export DOCKER_HOST="unix://$podman_socket"
    printf 'CONTAINER: Podman machine %s (%s)\n' "$machine_name" "$DOCKER_HOST"
    exec act \
        --container-daemon-socket "$daemon_socket" \
        --container-options "--security-opt label=disable" \
        "$@"
}

if command -v podman >/dev/null 2>&1; then
    if ! run_with_podman "$@"; then
        printf 'WARN: Podman machine %s is unavailable; trying Docker\n' "$machine_name" >&2
    fi
fi

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    printf 'CONTAINER: Docker fallback (%s)\n' "${DOCKER_HOST:-default context}"
    exec act "$@"
fi

printf 'FAIL: neither %s nor a running Docker daemon is available\n' "$machine_name" >&2
exit 2
