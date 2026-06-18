# Phase2 Verdict Casing Reconcile

PM SIGN-OFF: APPROVED

## Question

TODO §6 carried a warning that Phase2 promotion could be permanently blocked because Rust emitted lowercase `eligible` while Python compared against `"Eligible"`.

## Finding

The warning is stale. Current source has a shared Python contract:

- `app/strategist_promote_contract.py`: `ELIGIBLE_TOKEN = "eligible"` and `is_eligible()` lowercases before comparison.
- `app/strategist_promote_routes.py`: promote criteria gate calls `is_eligible(verdict)`.
- `rust/openclaw_engine/src/ipc_server/dispatch.rs`: response uses `verdict.tag()`.
- `tests/test_strategist_promote_phase2.py`: casing contract test asserts lowercase Rust tag and tolerant Python comparison.

## Validation

- `PYTHONPATH=. python3 -m pytest tests/test_strategist_promote_phase2.py::TestIpcContractKeysAndCasing::test_verdict_casing_handler_emits_what_route_consumes -q` -> 1 passed.
- Full `tests/test_strategist_promote_phase2.py` under `/usr/local/bin/python3` 3.10 returned 21 passed / 2 failed; both failures were `tomllib` missing false-reds in real-config tests.
- Local Python 3.12 has `tomllib` but no pytest installed, so full 3.12 rerun was unavailable.

## Boundary

Read-only source/test reconcile only. No code, runtime, DB, auth, risk, order, or trading mutation.
