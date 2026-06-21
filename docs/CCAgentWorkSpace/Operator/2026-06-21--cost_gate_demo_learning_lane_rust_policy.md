# Cost-Gate Demo-Learning Lane Rust Policy Seam

## Status

Implemented a source-only Rust policy module for the bounded cost-gate demo-learning lane.

This is not active order routing. The current plan still has:

- `main_cost_gate_adjustment=NONE`
- `order_authority=NOT_GRANTED`

So matching selected side-cells remain rejected with `ORDER_AUTHORITY_NOT_GRANTED`.

## What Changed

- New Rust module: `rust/openclaw_engine/src/demo_learning_lane.rs`
- New Rust tests: `rust/openclaw_engine/src/demo_learning_lane_tests.rs`
- The policy mirrors the Python runtime Adapter in Rust authority code.
- Future plan/scorecard timestamps now fail closed in both Python and Rust.

## What It Checks

- demo/live_demo mode
- selected side-cell
- `cost_gate_js_demo_negative_edge`
- candidate guardrails
- budget
- cooldown
- failed probe outcomes
- manual side-cell disable rows
- risk state
- explicit `DEMO_LEARNING_PROBE_GRANTED`
- adapter enablement

## Verification

- Rust learning-lane tests: 7 passed.
- Existing Rust cost-gate focused tests: 26 passed.
- Python learning-lane tests: 11 passed.
- Python compile: passed.

## Boundary

No DB write, no Bybit private/signed/trading call, no deploy/restart, no runtime config change, no risk/auth/order mutation.

Next step is operator-reviewed Rust hot-path wiring plus durable probe outcome labels, not global cost-gate lowering.
