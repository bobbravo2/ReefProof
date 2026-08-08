#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$repository_root/.cache/uv}"

if command -v uv >/dev/null 2>&1; then
  exec uv run --quiet python -m reefproof.usage "$@"
fi

if command -v python3.13 >/dev/null 2>&1; then
  PYTHONPATH="$repository_root/src${PYTHONPATH:+:$PYTHONPATH}" \
    exec python3.13 -m reefproof.usage "$@"
fi

printf 'FAIL: uv or Python 3.13 is required\n' >&2
exit 1
