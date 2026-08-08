#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
PROMPT_FILE="$SCRIPT_DIR/1-shot-eval-benchmark.prompt.txt"
RESULTS_ROOT="$PROJECT_ROOT/.local/1-shot-results"
RUN_DIR="$RESULTS_ROOT/reefproof-startup-benchmark-$(date '+%Y%m%d-%H%M%S')"
START_SECONDS=$SECONDS

if [[ ! -f "$PROMPT_FILE" ]]; then
  printf 'missing prompt file: %s\n' "$PROMPT_FILE" >&2
  exit 1
fi

mkdir -p "$RUN_DIR"
cd "$PROJECT_ROOT"

cp "$PROMPT_FILE" "$RUN_DIR/prompt.txt"

{
  printf 'captured_at_utc='
  date -u '+%Y-%m-%dT%H:%M:%SZ'
  printf 'working_directory=%s\n' "$PWD"
  printf 'codex_version='
  codex --version 2>/dev/null
  printf 'branch='
  git branch --show-current
  printf 'head='
  git rev-parse HEAD
  printf '\ncontext_file_sizes:\n'
  wc -lc \
    AGENTS.md \
    .agent/project-context.json \
    .agent/next-task.md
  printf '\ncontext_file_hashes:\n'
  shasum -a 256 \
    AGENTS.md \
    .agent/project-context.json \
    .agent/next-task.md
} >"$RUN_DIR/meta.txt" 2>&1

git status --porcelain=v1 >"$RUN_DIR/git-before.txt"

stderr_raw="$RUN_DIR/stderr-and-time.raw"
if /usr/bin/time -l codex exec --json --output-last-message "$RUN_DIR/final-message.txt" <"$PROMPT_FILE" \
  >"$RUN_DIR/events.jsonl" \
  2>"$stderr_raw"
then
  codex_exit_code=0
else
  codex_exit_code=$?
fi

sed '/^WARNING: proceeding, even though we could not create PATH aliases: Operation not permitted (os error 1)$/d' \
  "$stderr_raw" >"$RUN_DIR/stderr-and-time.txt"
rm -f "$stderr_raw"

printf '%s\n' "$codex_exit_code" >"$RUN_DIR/exit-code.txt"

codex_version=$(codex --version 2>/dev/null)
uv run python scripts/summarize-codex-benchmark.py \
  --events "$RUN_DIR/events.jsonl" \
  --final-message "$RUN_DIR/final-message.txt" \
  --codex-version "$codex_version" \
  --wall-seconds "$((SECONDS - START_SECONDS))" \
  --output "$RUN_DIR/efficiency-summary.json"

git status --porcelain=v1 >"$RUN_DIR/git-after.txt"

if cmp -s "$RUN_DIR/git-before.txt" "$RUN_DIR/git-after.txt"; then
  printf 'UNCHANGED\n' >"$RUN_DIR/repository-state-result.txt"
else
  printf 'CHANGED\n' >"$RUN_DIR/repository-state-result.txt"
fi

printf 'Benchmark complete.\n'
printf 'Results directory:\n%s\n' "$RUN_DIR"
printf 'Efficiency summary:\n'
sed -n '1,120p' "$RUN_DIR/efficiency-summary.json"
