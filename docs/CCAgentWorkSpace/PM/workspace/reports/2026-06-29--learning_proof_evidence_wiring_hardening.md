# Learning Proof Evidence Wiring Hardening

Date: 2026-06-29
Owner: PM
Status: DONE_WITH_CONCERNS

## Demo Key Finding

The observed key is in the Bybit Demo API slot, not the live/mainnet key.

Correction on 2026-06-30: the operator confirmed in the Bybit Demo API page that the masked Demo key `FWkGZX...g53T` is correct, Read-Write, and OpenAPI IP-whitelisted to `79.117.10.224`. The previous `BHw4...` expected-prefix mismatch is a stale expected-hint false positive, not evidence that the Demo key is wrong and not a live/mainnet key issue. Connector cutover still remains blocked by runtime mode state, so `BYBIT_MODE=read_only` and `BYBIT_CONNECTOR_WRITE_ENABLED=false` are still expected fail-closed state until a reviewed Demo-only cutover is applied.

## Source Changes

- Added `helper_scripts/research/cost_gate_learning_lane/learning_candidate_proof_evidence.py`, an artifact-only producer for `cost_gate_learning_candidate_proof_evidence_v1`.
- Hardened `learning_proof_promotion_gate.py` so candidate fills and matched controls must exact-match side-cell, strategy, symbol, side, and outcome horizon before counting as proof.
- Hardened proof/serving authority scans to catch truthy `*_allowed_by_this_packet` aliases.
- Hardened `learning_stack_health_snapshot.py` so cron expected-head pins are parsed and compared against the target head; stale/missing pins now emit explicit scheduler blockers.
- Updated `helper_scripts/SCRIPT_INDEX.md` and focused regression tests.

## Runtime Hygiene

Read-only check of `http://100.91.109.86:8000/openapi.json` returned `200`. The previous `/openapi.json` 500 is not the current blocker in this checkpoint.

## Verification

- `py_compile` for touched helpers/tests: PASS
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_candidate_proof_evidence.py helper_scripts/research/tests/test_cost_gate_learning_proof_promotion_gate.py helper_scripts/research/tests/test_cost_gate_learning_serving_snapshot.py` -> `31 passed`
- `python3 -m pytest -q helper_scripts/cron/tests/test_learning_stack_health_snapshot.py` -> `8 passed`
- `git diff --check` -> PASS

## Boundary

No secret write, env mutation, service restart, cron install/edit, PG query/write, Bybit call, Decision Lease, order action, Cost Gate change, model load, registry write, serving slot write, live/mainnet authority, promotion authority, or profit proof occurred.

This closes the MIT source-wiring gap for producing proof-evidence packets, but it does not make runtime promotion-ready. The real runtime still needs a fresh readiness rerun with corrected expected-key handling, reviewed Demo connector cutover, serving repair closure, fresh final-window execution gates, and actual candidate-matched Demo fills.
