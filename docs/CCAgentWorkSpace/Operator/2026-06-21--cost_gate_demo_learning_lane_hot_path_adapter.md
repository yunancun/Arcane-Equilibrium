# Cost-Gate Demo-Learning Lane Hot-Path Adapter

## Status

Implemented a Rust source-only hot-path adapter for recognizing eligible demo/live_demo cost-gate rejects as learning-lane events.

Current selected side-cells still have:

- `main_cost_gate_adjustment=NONE`
- `order_authority=NOT_GRANTED`

So this does not create active order routing.

## What Changed

- New Rust module: `rust/openclaw_engine/src/demo_learning_lane_hot_path.rs`
- New focused tests: `rust/openclaw_engine/src/demo_learning_lane_hot_path_tests.rs`
- Exchange-gate reject path now recognizes `cost_gate_js_demo_negative_edge` rejects in `demo`/`live_demo`.
- Recognition currently emits a debug trace only; it does not append the ledger yet.

## Verification

- Rust learning-lane tests: 15 passed.
- Rust cost-gate focused tests: 26 passed.
- New-file rustfmt check: passed.
- `git diff --check`: passed.

## Boundary

No DB write, no Bybit private/signed/trading call, no deploy/restart, no runtime config change, no risk/auth/order mutation, no main cost-gate relaxation.

Next step is append-only ledger wiring for every recognized eligible reject, then fill-backed outcomes and edge-estimate feedback.
