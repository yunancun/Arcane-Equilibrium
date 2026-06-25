# Bounded Probe Active Order Wiring Contract

- Date: 2026-06-24
- Blocker: `P0-BOUNDED-PROBE-ACTIVE-ORDER-WIRING-SOURCE-CONTRACT-DEMO-ONLY`
- Status: `DONE_WITH_CONCERNS`
- Boundary: source/test/docs only; no runtime sync, no `/tmp` runtime artifact, no latest/plan/admission/ledger mutation, no PG/Bybit/API/order/service/env/crontab action, no Rust writer enablement, no Cost Gate lowering, no live/mainnet, no active probe/order authority, and no promotion proof.

## What Changed

Added `helper_scripts/research/cost_gate_learning_lane/bounded_probe_active_order_wiring_contract.py`.

The helper emits `bounded_demo_probe_active_order_wiring_contract_v1` and defines the source contract that must exist before any active bounded Demo probe can move to E3/BB exchange-facing review:

- dedicated Rust active-order module
- demo/live_demo one-order bounded limits
- post-only near-touch limit-or-skip order envelope
- Guardian/risk/operator/Decision Lease/Rust authority gates
- dispatch through existing `OrderDispatchRequest`
- candidate-matched attempt, order, fill, fee, slippage, and matched-control lineage

`ACTIVE_ORDER_WIRING_CONTRACT_READY_FOR_E3_BB_REVIEW` is only review readiness. It does not grant probe/order/live authority or allow any order submission.

PA/E1 and E2 findings were closed in source: authority contamination now rejects truthy/grant-like string/int aliases and adjacent deny-pattern aliases such as PG/API/private endpoint/service/order mutation fields; future READY requires non-comment/non-string/non-macro code-like evidence rather than marker strings; authority-path patch readiness now code-scans both existing and required seams and requires every guard/lineage seam, not only adapter and dispatch presence; and Rust raw/ordinary multiline strings plus macro invocation token trees are stripped before evidence matching so marker text cannot leak into the code scan.

## Current Repo Result

CLI smoke on current source returns `ACTIVE_ORDER_WIRING_SOURCE_PATCH_REQUIRED`.

Missing source requirements:

- `bounded_probe_active_order_module_missing`
- `demo_only_bounded_order_limits_missing`
- `post_only_near_touch_order_envelope_missing`
- `guardian_decision_lease_rust_authority_gate_missing`
- `tick_dispatch_active_bounded_probe_exchange_wiring_missing`
- `candidate_matched_order_fill_fee_slippage_lineage_missing`

Active-order blockers remain:

- `demo_learning_lane_writer_contract_no_order_submission`
- `demo_learning_lane_writer_adapter_enabled_false`
- `tick_dispatch_records_preview_no_order_submitted`
- `near_touch_adapter_contract_pure_no_order_math`
- `positive_active_order_submission_evidence_missing`

## Verification

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_active_order_wiring_contract.py` -> `16 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_authority_patch_readiness.py` -> `23 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_active_order_wiring_contract.py helper_scripts/research/tests/test_cost_gate_bounded_probe_authority_patch_readiness.py helper_scripts/research/tests/test_cost_gate_bounded_probe_plan_inclusion_review.py helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py` -> `63 passed`
- CLI smoke confirmed current source is patch-required with all authority/order/runtime/PG answers false.

## Next

Next blocker: source-only Rust implementation patch for active bounded Demo order wiring. Do not proceed to E3/BB order envelope until this contract reports review-ready, and do not treat review-ready as order authority.
