---
name: reefproof-cli-startup-benchmark
description: Measure and compare ReefProof CLI process startup latency through the real ./reefproof launcher, with isolated local state, bounded repetitions, JSON evidence, and an optional median regression threshold. Use for CLI startup timing, cold or warm launcher comparisons, startup regression checks, and development-versus-packaged CLI performance investigations.
---

# ReefProof CLI startup benchmark

Run project grounding and inspect Git state before measuring. Do not benchmark
while another writer is changing the launcher, CLI imports, dependency lock, or
benchmark skill; report the run as contaminated instead.

Use `scripts/benchmark.py` from the repository root. The default performs one
development-launcher measurement of `./reefproof --help`:

```bash
python .codex/skills/reefproof-cli-startup-benchmark/scripts/benchmark.py
```

Select repetitions deliberately. Use one run for an ordinary snapshot, one
before and one after an optimization, or an explicit bounded count when the
user requests variance evidence:

```bash
python .codex/skills/reefproof-cli-startup-benchmark/scripts/benchmark.py \
  --runs 5 --warmups 1 --label warm-help
```

Pass another non-interactive CLI route after `--`. Never benchmark `serve`,
`menu`, a live transport, or a mutating operation:

```bash
python .codex/skills/reefproof-cli-startup-benchmark/scripts/benchmark.py \
  --label version -- ./reefproof --version
```

Use `--max-median-ms` only for an accepted machine-local regression budget. A
threshold failure exits 1. A CLI invocation failure exits 2. Results are saved
under ignored `.local/qa-bench/cli-startup/` unless `--output` is supplied.
The default help benchmark also requires its expected ReefProof help marker.
For another command, pass `--expect TEXT` to prevent a wrongly empty or partial
result from appearing as a startup improvement.

Report the command, launcher mode, run and warmup counts, median/min/max timing,
output stability, threshold result, output path, exit status, and boundary
measured. Use the per-run byte counts and SHA-256 digests to detect behavior or
rendering changes before comparing latency. Treat
cross-machine comparisons and development-versus-packaged comparisons as
different populations. Do not claim interactive prompt readiness from a
`--help` measurement.
