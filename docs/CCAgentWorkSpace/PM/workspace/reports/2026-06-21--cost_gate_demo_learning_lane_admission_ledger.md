# Cost-Gate Demo-Learning Lane Admission Ledger

## Summary

This batch adds the Rust authority-layer admission ledger builder for the bounded cost-gate demo-learning lane.

It does not wire order dispatch, grant order authority, lower the main cost gate, connect to PG, call Bybit, or mutate runtime config.

## Why

Demo needs to become a learning system, not only a controlled order path. When cost gate rejects a selected side-cell, the Rust authority layer must be able to emit a durable learning record before any future probe order is considered.

The previous Rust seam could decide admission, but it did not produce the append-only evidence row that the learning lane uses for budget, cooldown, and outcome-disable feedback.

## Implementation

- Added `rust/openclaw_engine/src/demo_learning_lane_ledger.rs`.
- Exported `openclaw_engine::demo_learning_lane_ledger`.
- Added `build_admission_ledger_record(...)` to convert a Rust `AdmissionDecision` plus `RejectEvent` into `record_type=probe_admission_decision`.
- Added stable `attempt_id` generation:
  - `context_id`
  - then `signal_id`
  - then `side_cell_key|ts_ms`
- Normalized ledger event fields:
  - side-cell key
  - strategy, symbol, side
  - normalized reject reason
  - lowercased engine mode
  - event timestamp
- Extended the Rust ledger reader to understand nested `event.ts_ms`, `attempt_id`, `allowed_to_submit_order`, reason, and boundary metadata.

## Guardrails

- Ledger record is artifact-only evidence.
- `ORDER_AUTHORITY_NOT_GRANTED` decisions are still recordable, but `allowed_to_submit_order=false`.
- Boundary string explicitly says no PG, Bybit, order, config, risk, auth, or runtime mutation.
- Current latest plan remains `order_authority=NOT_GRANTED`.
- Existing cost-gate behavior is unchanged.

## Verification

- `rustfmt --edition 2021 --check rust/openclaw_engine/src/demo_learning_lane.rs rust/openclaw_engine/src/demo_learning_lane_ledger.rs rust/openclaw_engine/src/demo_learning_lane_tests.rs` -> passed.
- `cargo test -p openclaw_engine demo_learning_lane --lib` -> 10 passed.
- `cargo test -p openclaw_engine test_cost_gate_moderate --lib` -> 26 passed.

Note: full `cargo fmt --all --check` was not used as a gate because the existing workspace has broad pre-existing rustfmt drift outside this batch.

## Boundary

Source/test/docs only. No PG write, schema migration, Bybit private/signed/trading call, engine/API rebuild or restart, credential/auth/risk/order/strategy/runtime mutation, signal proof, execution proof, or promotion proof.

## Next

Operator-reviewed Rust demo hot-path wiring should append this ledger row for every eligible cost-gate rejection. Only after that should any demo-only probe order authority be considered, and it still needs fill-backed outcome labels plus edge-estimator feedback.
