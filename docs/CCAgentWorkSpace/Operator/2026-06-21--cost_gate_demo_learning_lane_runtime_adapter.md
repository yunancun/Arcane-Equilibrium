# Cost-Gate Demo-Learning Lane Runtime Adapter

## Status

Implemented source-only admission/ledger Adapter for the bounded demo-learning lane.

Current selected side-cells can now be matched against the plan, but the current plan still has:

- `main_cost_gate_adjustment=NONE`
- `order_authority=NOT_GRANTED`

So matching signals return `ORDER_AUTHORITY_NOT_GRANTED`, not an order.

## What Changed

- New module: `helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py`
- New decision schema: `cost_gate_demo_learning_lane_adapter_v1`
- New ledger record shape: `probe_admission_decision`
- Budget, cooldown, and failed-outcome auto-disable logic are now test-covered.

## Verification

- Python adapter/plan tests: 9 passed.
- Adjacent scorecard + adapter tests: 15 passed.
- Python compile: passed.
- Rust cost-gate focused tests: 26 passed.

## Boundary

No DB write, no Bybit private/signed/trading call, no deploy/restart, no runtime config change, no risk/auth/order mutation.

Next step is operator-reviewed Rust hot-path wiring plus durable outcome labels, not global cost-gate lowering.
