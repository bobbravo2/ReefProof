#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
binary_path="${1:-$repository_root/dist/reefproof}"
binary_directory="$(cd "$(dirname "$binary_path")" && pwd)"
binary_path="$binary_directory/$(basename "$binary_path")"
expected_revision="${2:-$(git -C "$repository_root" rev-parse HEAD)}"
archive_viewer="${PYI_ARCHIVE_VIEWER:-pyi-archive_viewer}"
artifact_listing="$(mktemp)"
artifact_output="$(mktemp)"
runtime_output="$(mktemp)"
execution_root="$(mktemp -d)"
trap 'rm -f "$artifact_listing" "$artifact_output" "$runtime_output"; rm -rf "$execution_root"' EXIT

if [[ ! -x "$binary_path" ]]; then
  printf 'FAIL: binary is missing or not executable: %s\n' "$binary_path" >&2
  exit 1
fi

"$archive_viewer" -r "$binary_path" >"$artifact_listing"

if ! grep -Fq "reefproof/storage/migrations/env.py" "$artifact_listing"; then
  printf 'FAIL: binary does not contain the Alembic migration environment\n' >&2
  exit 1
fi

for forbidden in \
  "$repository_root" \
  "/Users/" \
  "direct_url.json" \
  "_pytest" \
  "pytest" \
  "pyright" \
  "ruff" \
  "setuptools"; do
  if grep -Fq "$forbidden" "$artifact_listing"; then
    printf 'FAIL: binary contains forbidden development artifact: %s\n' "$forbidden" >&2
    exit 1
  fi
done

(
  cd "$execution_root"
  "$binary_path" version >"$artifact_output"
  "$binary_path" --help >help.txt
  "$binary_path" doctor >doctor.txt
  REEFPROOF_DATA_DIRECTORY="$execution_root/data" \
    "$binary_path" infra-smoke --format json >"$runtime_output"
)

grep -Fq "Git commit: $expected_revision" "$artifact_output"
grep -Fq "Build state: packaged" "$artifact_output"
grep -Fq "infra-smoke" "$execution_root/help.txt"
grep -Fq "database" "$execution_root/help.txt"
grep -Fq "Doctor result:" "$execution_root/doctor.txt"

printf 'PASS: binary is isolated from local development state\n'
