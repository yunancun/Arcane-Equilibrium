# PM Report: Cost-Gate Learning Capture-Error Diagnostics

Date: 2026-06-21

## Objective

Close a remaining silent-drop ambiguity in the cost-gate demo-learning lane. If the Rust writer is enabled and sees an eligible demo/live_demo cost-gate reject, but admission evaluation cannot run because the plan/path/config is broken, the signal should become durable evidence instead of only a runtime warning.

## Change

- Added Rust `probe_capture_error` ledger rows.
- `probe_capture_error` uses `decision=ADMISSION_NOT_EVALUATED` and `allowed_to_submit_order=false`.
- The row preserves attempt id, side-cell, event identity, risk state, and the capture error.
- `cost_gate_learning_lane.status` now reports:
  - `capture_error_count`
  - `captured_reject_count`
  - `latest_capture_error`
  - `ledger_status=CAPTURE_ERRORS_PRESENT`
  - `status=CAPTURE_ERRORS_NEED_OPERATOR_FIX`
  - `answers.admission_evaluation_errors_recorded=true`
- Alpha discovery now routes capture-error-only ledgers to `cost_gate_capture_errors_present` / `cost_gate_rejects_captured_but_admission_not_evaluated`.

## Interpretation

This separates three states that previously could be confused:

- no ledger rows: likely not accumulating or no eligible rejects observed
- capture-error rows: rejects are being captured, but admission evaluation is broken
- admission rows: rejects were evaluated and can move to blocked-signal outcome refresh

This improves autonomous learning observability without granting order authority.

## Verification

- `cargo test -p openclaw_engine demo_learning_lane --lib` = 21 passed
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` = 38 passed
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = 34 passed
- `rustfmt --edition 2021 --check rust/openclaw_engine/src/demo_learning_lane_ledger.rs rust/openclaw_engine/src/demo_learning_lane_writer.rs rust/openclaw_engine/src/demo_learning_lane_tests.rs` passed

## Boundary

Source/test/docs only. No runtime enablement, deploy, restart, PG write/schema migration, Bybit private/signed/trading call, order authority, main Cost Gate lowering, credential/auth/risk/order/strategy/runtime mutation, signal proof, execution proof, or promotion proof.
