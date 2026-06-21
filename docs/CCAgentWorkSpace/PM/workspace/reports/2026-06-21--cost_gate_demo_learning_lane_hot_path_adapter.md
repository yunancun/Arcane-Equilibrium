# Cost-Gate Demo-Learning Lane Hot-Path Adapter

## Summary

This batch adds the Rust hot-path adapter that recognizes eligible demo/live_demo cost-gate rejects as learning-lane events.

It does not append the ledger yet, submit orders, grant order authority, lower the main cost gate, connect to PG, call Bybit, or mutate runtime config.

## Why

The earlier diagnosis showed demo had gone quiet because cost gate rejected signals before order creation. The learning lane now has a plan, policy, outcome writer, and admission ledger builder, but a real rejected signal still needed a Rust hot-path handoff point so it is not silently lost.

This checkpoint creates that handoff point while preserving the Rust authority boundary.

## Implementation

- Added `rust/openclaw_engine/src/demo_learning_lane_hot_path.rs`.
- Exported `openclaw_engine::demo_learning_lane_hot_path`.
- Added `demo_learning_lane_hot_path_tests.rs`.
- The adapter accepts `OrderIntent`, engine mode, reject reason, timestamp, context ID, and signal ID.
- It returns a `RejectEvent` only for:
  - engine mode `demo` or `live_demo`
  - normalized reason `cost_gate_js_demo_negative_edge`
  - non-zero timestamp
  - non-empty strategy and symbol
  - side-consistent `OpenLong`/`OpenShort` intent type
- It normalizes symbol casing, side, engine mode, reject reason, and blank context/signal IDs.
- `step_4_5_dispatch` now calls the adapter from the exchange-gate reject path and emits a `demo_learning_lane` debug trace when an eligible reject is recognized.

## Guardrails

- Pure adapter only: no IO, no DB, no Bybit, no plan evaluation, no ledger write.
- Hot-path call is recognition-only and does not alter order dispatch behavior.
- Current latest plan remains `order_authority=NOT_GRANTED`.
- Selected side-cells still remain `ORDER_AUTHORITY_NOT_GRANTED`.
- Main cost gate remains unchanged.

## Verification

- `cargo test -p openclaw_engine demo_learning_lane --lib` -> 15 passed.
- `cargo test -p openclaw_engine test_cost_gate_moderate --lib` -> 26 passed.
- `rustfmt --edition 2021 --check rust/openclaw_engine/src/demo_learning_lane_hot_path.rs rust/openclaw_engine/src/demo_learning_lane_hot_path_tests.rs` -> passed.
- `git diff --check` -> passed.

Note: full `cargo fmt --all --check` was not used as a gate because the existing workspace has broad pre-existing rustfmt drift outside this batch.

## Boundary

Source/test/docs only. No PG write, schema migration, Bybit private/signed/trading call, engine/API rebuild or restart, credential/auth/risk/order/strategy/runtime mutation, signal proof, execution proof, or promotion proof.

## Next

Wire an append-only runtime ledger sink for every recognized eligible reject, then add fill-backed outcome labels and edge-estimator feedback. Only after those exist should demo-only probe order authority be considered.
