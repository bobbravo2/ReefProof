#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

workbench_ts="src/reefproof/api/web/typescript/workbench.ts"
workbench_js="src/reefproof/api/web/static/workbench.js"

if ! command -v npm >/dev/null 2>&1; then
  printf 'FAIL: npm is required to validate generated workbench assets.\n' >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  printf 'FAIL: node is required to run generated workbench tests.\n' >&2
  exit 1
fi

if [[ ! -f "$workbench_ts" ]]; then
  printf 'FAIL: missing TypeScript source: %s\n' "$workbench_ts" >&2
  exit 1
fi

npm run build

if [[ ! -f "$workbench_js" ]]; then
  printf 'FAIL: missing generated bundle after build: %s\n' "$workbench_js" >&2
  exit 1
fi

node --test tests/web/workbench.test.cjs

printf 'PASS: generated workbench bundle rebuilt and tested.\n'
