#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

failures=0

pass() {
  printf 'PASS: %s\n' "$1"
}

fail() {
  printf 'FAIL: %s\n' "$1"
  failures=$((failures + 1))
}

required_files=(
  "AGENTS.md"
  "README.md"
  "CONTRIBUTING.md"
  ".agent/current-state.md"
  ".agent/next-task.md"
  ".agent/evals.yaml"
  "docs/product-context.md"
  "docs/architecture-decisions.md"
  "docs/open-questions.md"
  "docs/plans/README.md"
  "scripts/check-baseline.sh"
  "scripts/check-runtime-authority.py"
  ".github/pull_request_template.md"
  ".github/workflows/checks.yml"
  ".gitignore"
  ".editorconfig"
  ".env.example"
  "Makefile"
  "pyproject.toml"
  "uv.lock"
  "scripts/bootstrap.sh"
  "scripts/check-generated-workbench.sh"
  "scripts/check-generated-workbench-contracts.sh"
  "scripts/agent-usage.sh"
  ".codex/agents/reefproof-reviewer.toml"
  ".codex/skills/reefproof-project-grounding/SKILL.md"
  ".codex/skills/reefproof-project-grounding/scripts/extract.py"
)

missing_files=()
for required_file in "${required_files[@]}"; do
  if [[ ! -f "$required_file" ]]; then
    missing_files+=("$required_file")
  fi
done

if ((${#missing_files[@]} == 0)); then
  pass "required baseline files exist"
else
  for missing_file in "${missing_files[@]}"; do
    fail "missing required file: $missing_file"
  done
fi

permanent_invariant="ReefProof may observe, model, challenge, and alert on a living system. It may not silently take control of one."
if grep -Fq "$permanent_invariant" AGENTS.md; then
  pass "permanent product invariant is documented"
else
  fail "permanent product invariant is absent from AGENTS.md"
fi

if [[ -f ".agent/current-state.md" && -f ".agent/next-task.md" ]]; then
  pass "current state and next task exist"
else
  fail "current state or next task is missing"
fi

required_shell_files=(
  "src/reefproof/__init__.py"
  "src/reefproof/cli.py"
  "src/reefproof/settings.py"
  "src/reefproof/logging.py"
  "src/reefproof/doctor.py"
)
missing_shell_files=()
for shell_file in "${required_shell_files[@]}"; do
  if [[ ! -f "$shell_file" ]]; then
    missing_shell_files+=("$shell_file")
  fi
done
if ((${#missing_shell_files[@]} == 0)); then
  pass "Phase 0 product shell exists"
else
  for missing_shell_file in "${missing_shell_files[@]}"; do
    fail "missing Phase 0 shell file: $missing_shell_file"
  done
fi

stale_capability_descriptions=(
  "initial three-state invariant evaluation"
  "expanded invariant coverage"
)
stale_capability_found=0
for stale_description in "${stale_capability_descriptions[@]}"; do
  if grep -FRq "$stale_description" README.md src/reefproof/cli.py src/reefproof/doctor.py; then
    fail "stale user-visible capability description: $stale_description"
    stale_capability_found=1
  fi
done
if ((stale_capability_found == 0)); then
  pass "user-visible capability descriptions match the implemented offline product"
fi

if python3 scripts/check-runtime-authority.py; then
  pass "offline vendor evidence adds no live transport or MQTT capability"
else
  fail "runtime authority boundary validation failed"
fi

if ((failures > 0)); then
  printf 'FAIL: baseline validation found %d issue(s)\n' "$failures"
  exit 1
fi

pass "baseline validation complete"
