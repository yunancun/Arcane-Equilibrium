# Bounded Demo Key Expected Prefix False Positive Fix

Date: 2026-06-30
Owner: PM
Status: DONE_WITH_CONCERNS

## Verdict

The problematic API-key signal was in the Demo slot, not live/mainnet. The operator's Bybit Demo API page confirms masked `FWkGZX...g53T` is the correct Demo Read-Write key and is OpenAPI IP-whitelisted to `79.117.10.224`.

The previous `BHw4...` mismatch was a stale expected-prefix hint in the readiness invocation/artifact, not evidence that the stored Demo key was wrong. I changed the readiness guard so an expected Demo key sha/prefix mismatch is advisory by default; it becomes a credential blocker only when `--require-expected-demo-api-key-match` is explicitly supplied.

## Source Changes

- `helper_scripts/research/cost_gate_learning_lane/bounded_demo_runtime_readiness.py` now records `expected_key_match_required`.
- `demo_api_key_expected_value_mismatch` goes into `advisory_reasons` unless strict expected-key matching is requested.
- Added CLI flag `--require-expected-demo-api-key-match` for cases where operator-provided key pinning is intentionally authoritative.
- Regression coverage now proves both paths: advisory mismatch leaves credential readiness green and exposes connector-mode blockers; strict mismatch blocks credentials.

## Runtime Meaning

Current runtime remains blocked, but not because the Demo key is proven wrong:

- Connector mode still reports `BYBIT_MODE=read_only`.
- Connector write flag still reports `BYBIT_CONNECTOR_WRITE_ENABLED=false`.
- Existing proof scan still has no candidate-matched order/fill/fee/slippage/reconstruction evidence.
- Serving/proof promotion gates still require training/registry repair closure, row-backed candidate-matched fills, matched controls, execution realism, and proof-exclusion pass.

Next executable path is to rerun bounded Demo readiness without the stale `BHw4...` expected pin, or with a current strict expected key if pinning is desired; then apply the reviewed Demo-only connector cutover if readiness is green; then rerun final-window BBO, Decision Lease, Guardian/Rust authority, GUI cap, auditability, and reconstructability gates before any bounded Demo order attempt.

## Verification

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/bounded_demo_runtime_readiness.py helper_scripts/research/tests/test_cost_gate_bounded_demo_runtime_readiness.py` -> PASS
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_demo_runtime_readiness.py helper_scripts/research/tests/test_cost_gate_bounded_demo_credential_mode_cutover_preflight.py` -> `11 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_settings_bybit_demo_connector_mode.py` -> `6 passed`

## Boundary

No secret write, env mutation, service restart, cron edit/install, PG query/write, Bybit private call, credential validation call, Decision Lease, order/cancel/modify, Cost Gate change, model load, registry write, serving slot write, live/mainnet authority, promotion authority, or profit proof occurred.
