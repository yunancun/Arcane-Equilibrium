# PM Report - NEAR Buy Order-Capable Gate Blocked By Soak Plan

Status: `HARD_BLOCKED_NO_SAFE_ACTION`

Candidate: `ma_crossover|NEARUSDT|Buy`

Active blocker: `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE`

## What Changed

PM continued after the same-window no-order final gate and did not perform any order-capable runtime action.

Source repair completed:

- `current_candidate_order_capable_demo_invoke_review_packet.py` now accepts the current compact `renewed_active_bbo_execution_manifest_v1` shape.
- Compact manifest approval is not inferred from bare hashes. The packet now verifies E3/BB report path, sha256, and `VERDICT: APPROVE_WITH_CONDITIONS`.
- Compact authority aliases and `active_answers` contamination now fail closed; compact post-governance loss-control state is also validated.
- Future public market-data scope now uses the candidate symbol, so the NEAR packet lists `NEARUSDT` instead of stale `ETHUSDT`.
- Added `current_candidate_order_fill_evidence_scan_strict.py`, a read-only artifact producer for candidate-matched strict order/fill evidence.

Verification:

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_current_candidate_order_capable_demo_invoke_review_packet.py helper_scripts/research/tests/test_current_candidate_order_fill_evidence_scan_strict.py` -> `19 passed`
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/current_candidate_order_fill_evidence_scan_strict.py helper_scripts/research/cost_gate_learning_lane/current_candidate_order_capable_demo_invoke_review_packet.py` -> pass

## Runtime Artifact Reads

All runtime artifact access was read-only via `ssh`/`scp` from `trade-core`.

- Source checkpoint after repair: `84132cc3b8a6e9ba118d0823353a4f9ec9735406`
- Linux source head/origin after source-only sync: `84132cc3b8a6e9ba118d0823353a4f9ec9735406`
- Linux worktree: clean
- Standing Demo auth sha: `05fe07f5ad4f92c459c4c6f67bfe534a04b0ea4b4e8f2d8aa43879d87009152f`
- Bounded operator auth readiness sha: `7abf1233021f9dce8ce6772bfcae7ecebaeb0a2429786c8d2e2540c49bc0ccb9`, `decision=defer`, no authorization object
- Canonical bounded Demo soak plan sha: `30056993b5cae70a0fcad0503221e12bd74dae4e42a29d0d2c88423c64739823`
- Renewed no-order execution manifest sha: `17a3a426f31cbff6c0180dfdd239ea6b0ef2b132df486dfc76764825963cf321`

## New Evidence

Strict NEAR order/fill scan:

- Path: `/tmp/openclaw_order_capable_near_20260708T184751Z_84132cc3/outputs/current_candidate_order_fill_evidence_scan_strict.json`
- Sha256: `3453ac4f46e083650eed973189de61920b52ed5bc2bb577aa0f5c2a79a06ac6c`
- Status: `NO_CANDIDATE_MATCHED_ACTUAL_ORDER_FILL_EVIDENCE`
- Candidate rows: `0`
- Snapshot strict hits: `0`
- Engine log strict tail hits: `0`

Order-capable review packet:

- Path: `/tmp/openclaw_order_capable_near_20260708T184751Z_84132cc3/outputs/order_capable_demo_invoke_review_packet.json`
- Sha256: `9b39f4f72d35e9d2f90a1f536bdb53cfe077ac8a8059886a2ab1d1c9ca02ed46`
- Status: `CURRENT_CANDIDATE_ORDER_CAPABLE_DEMO_INVOKE_REVIEW_PACKET_BLOCKED_BY_LOSS_CONTROL`
- Authority boundary violations: `[]`
- Renewed no-order BBO blockers: `[]`
- Strict order/fill scan blockers: `[]`
- Future Phase A public scope: `GET /v5/market/time`, `GET /v5/market/tickers?category=linear&symbol=NEARUSDT`, `GET /v5/market/instruments-info?category=linear&symbol=NEARUSDT`

Remaining blockers:

- `soak_plan_candidate_mismatch`
- `soak_plan_operator_auth_candidate_mismatch`
- `soak_plan_operator_auth_expired`

The blocker is real: canonical runtime soak plan is still `grid_trading|ETHUSDT|Buy` and its embedded operator authorization expired at `2026-07-01T09:02:17.250395+00:00`.

## Boundary

No Bybit public/private/order call, no Decision Lease acquire/release, no order/probe/cancel/modify, no PG/DB query/write, no runtime/env/service/crontab mutation, no canonical plan write, no `_latest` write, no Cost Gate lowering, no live/mainnet action, and no proof/promotion claim occurred.

## Decision

Stop as `HARD_BLOCKED_NO_SAFE_ACTION` for the current order-capable branch.

Safe source/artifact routes tried:

1. Repaired the order-capable packet producer and validation contract.
2. Added and ran a strict candidate-matched order/fill evidence producer.
3. Inspected the bounded authorization and soak-plan rematerialization contracts; remaining plan repair requires a valid authorization object and reviewed materialization scope.

Next progress requires explicit operator authorization for `ma_crossover|NEARUSDT|Buy`, then a separate E3/BB-reviewed plan-inclusion/materialization scope before any order-capable final window can be opened.
