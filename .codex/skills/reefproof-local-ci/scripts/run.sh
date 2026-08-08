#!/usr/bin/env bash
set -euo pipefail

skill_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
repository_root="$(cd -- "$skill_directory/../../.." && pwd)"

usage() {
    printf '%s\n' \
        'Usage: run.sh [--print] TASK' \
        '' \
        'Tasks:' \
        '  list                       Show this catalog' \
        '  local-check                Canonical local quality gate' \
        '  local-binary               Verified standalone binary build' \
        '  local-bundle               Verified complete distribution bundle' \
        '  act-checks                 GitHub Actions checks job' \
        '  act-delivery-binary-linux  Linux delivery binary job' \
        '  act-delivery-container     Delivery OCI job via Podman'
}

print_only=false
if [[ "${1:-}" == "--print" ]]; then
    print_only=true
    shift
fi

if [[ $# -ne 1 ]]; then
    usage >&2
    exit 2
fi

task="$1"
case "$task" in
    list)
        usage
        exit 0
        ;;
    local-check)
        command=(make test/check)
        ;;
    local-binary)
        command=(make build/binary)
        ;;
    local-bundle)
        command=(make build)
        ;;
    act-checks)
        command=(
            ./scripts/run-act.sh pull_request
            --workflows .github/workflows/checks.yml
            --job check
            --pull=false
        )
        ;;
    act-delivery-binary-linux)
        command=(
            ./scripts/run-act.sh pull_request
            --workflows .github/workflows/delivery.yml
            --job binary
            --matrix os:ubuntu-latest
            --pull=false
        )
        ;;
    act-delivery-container)
        command=(
            ./scripts/run-act.sh pull_request
            --workflows .github/workflows/delivery.yml
            --job container
            --pull=false
        )
        ;;
    *)
        printf 'FAIL: unknown local CI task: %s\n' "$task" >&2
        usage >&2
        exit 2
        ;;
esac

cd "$repository_root"

if "$print_only"; then
    printf 'Repository: %s\nTask: %s\nCommand:' "$repository_root" "$task"
    printf ' %q' "${command[@]}"
    printf '\n'
    exit 0
fi

printf 'RUN: %s\n' "$task"
"${command[@]}"
printf 'PASS: %s\n' "$task"
