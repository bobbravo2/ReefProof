#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

if ! command -v npm >/dev/null 2>&1; then
  printf 'FAIL: npm is required to validate generated workbench contracts.\n' >&2
  exit 1
fi

npm run contracts:check
printf 'PASS: generated workbench contracts are synchronized.\n'
