# Bounded pytest development parallelism

## Outcome

Make the default developer Python test path use bounded pytest-xdist
parallelism while preserving `PYTEST_ARGS` as an explicit override.

## Accepted choice

Use eight workers (`-n 8`) rather than unbounded `auto`. The measured local
full suite stays within the 15-second Service budget with less risk of worker
oversubscription.

## Evidence

- Serial baseline: 428 passed, 31.41s pytest time, 32.96s wall time.
- Eight workers: 428 passed, 12.47s pytest time, 13.94s wall time.
- Final configured default: 428 passed, 12.35s pytest time, 13.76s wall time.

## Boundary

This changes development/test execution only. It does not alter production
runtime behavior, live transports, HYDROS authority, or release publication.
