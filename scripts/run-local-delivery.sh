#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

exec ./scripts/run-act.sh pull_request \
    --workflows .github/workflows/delivery.yml \
    --job container \
    --pull=false \
    "$@"
