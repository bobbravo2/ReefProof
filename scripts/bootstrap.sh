#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

if ! command -v python3.13 >/dev/null 2>&1; then
  printf 'FAIL: Python 3.13 is required. Install it with Homebrew: brew install python@3.13\n' >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  printf 'FAIL: uv is required. Install it with Homebrew: brew install uv\n' >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  printf 'FAIL: npm is required to verify the strict TypeScript frontend.\n' >&2
  exit 1
fi

export UV_CACHE_DIR="${UV_CACHE_DIR:-$repository_root/.cache/uv}"
uv sync --locked
npm ci
npm run browser:install
npm run build
chmod +x \
  scripts/check-generated-workbench.sh \
  scripts/check-generated-workbench-contracts.sh \
  .githooks/pre-commit
git config core.hooksPath .githooks
mkdir -p .local/data
printf 'PASS: ReefProof Phase 0 development environment is ready\n'
