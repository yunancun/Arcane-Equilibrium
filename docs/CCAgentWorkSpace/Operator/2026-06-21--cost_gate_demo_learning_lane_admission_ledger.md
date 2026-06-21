# Cost-Gate Demo-Learning Lane Admission Ledger

## Status

Implemented a Rust source-only admission ledger builder for the bounded cost-gate demo-learning lane.

Current selected side-cells still have:

- `main_cost_gate_adjustment=NONE`
- `order_authority=NOT_GRANTED`

So this does not create active order routing.

## What Changed

- New Rust module: `rust/openclaw_engine/src/demo_learning_lane_ledger.rs`
- Rust can now turn an admission decision into a `probe_admission_decision` JSONL row.
- The row carries stable `attempt_id`, normalized reject event, runtime state, decision, reason, and explicit artifact-only boundary.
- Existing Rust runtime-state reader now replays nested `event.ts_ms`, so admitted records feed budget/cooldown accounting.

## Verification

- Rust learning-lane tests: 10 passed.
- Rust cost-gate focused tests: 26 passed.
- Touched-file rustfmt check: passed.

## Boundary

No DB write, no Bybit private/signed/trading call, no deploy/restart, no runtime config change, no risk/auth/order mutation, no main cost-gate relaxation.

Next step is operator-reviewed hot-path wiring to record every eligible cost-gate rejection into this ledger, then fill-backed outcomes and edge-estimate feedback.
