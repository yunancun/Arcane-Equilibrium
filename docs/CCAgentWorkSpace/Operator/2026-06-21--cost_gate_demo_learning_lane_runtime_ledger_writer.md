# Cost-Gate Demo-Learning Lane Runtime Ledger Writer

## Status

Implemented source-only Rust wiring for an env-gated runtime ledger writer.

Default state is disabled. No runtime deploy/restart or writer enablement was performed in this batch.

## What Changed

- New Rust module: `rust/openclaw_engine/src/demo_learning_lane_writer.rs`
- Writer handle is spawned from `main.rs` and passed into paper/demo/live pipelines.
- Eligible demo/live_demo `cost_gate_js_demo_negative_edge` exchange-gate rejects can be recorded as append-only `probe_admission_decision` JSONL rows.
- Default ledger path: `$OPENCLAW_DATA_DIR/cost_gate_learning_lane/probe_ledger.jsonl`
- Enable flag: `OPENCLAW_DEMO_LEARNING_LANE_WRITER=1|true`

## Important Boundary

This is learning-data capture, not trading authorization.

- `main_cost_gate_adjustment=NONE`
- `order_authority=NOT_GRANTED`
- Writer enablement cannot submit orders.
- Writer enablement cannot lower the main cost gate.
- The writer hard-codes adapter enablement to false during admission evaluation.

With the current plan, matching selected side-cells still record `ORDER_AUTHORITY_NOT_GRANTED`.

## Verification

- Rust learning-lane tests: 19 passed.
- Rust cost-gate focused tests: 26 passed.
- New-writer rustfmt check: passed.
- `git diff --check`: passed.

## Operator Next Step

If we want live demo to accumulate rejected-signal learning evidence, the next action is an explicit deploy/enable decision for `OPENCLAW_DEMO_LEARNING_LANE_WRITER`, followed by checking that new eligible rejects append JSONL rows. This should happen before any discussion of demo probe order authority.
