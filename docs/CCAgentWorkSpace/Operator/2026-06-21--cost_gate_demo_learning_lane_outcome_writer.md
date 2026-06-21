# Cost-Gate Demo-Learning Lane Outcome Writer

## Status

Implemented source-only outcome writer infrastructure for the bounded cost-gate demo-learning lane.

Current selected side-cells still have:

- `main_cost_gate_adjustment=NONE`
- `order_authority=NOT_GRANTED`

So this does not create active order routing.

## What Changed

- New constants module: `helper_scripts/research/cost_gate_learning_lane/contract.py`
- New outcome module: `helper_scripts/research/cost_gate_learning_lane/outcome_writer.py`
- `runtime_adapter.py` can now run `--record-outcomes --price-observations ...` to append matured `probe_outcome` ledger rows.
- Outcome rows are idempotent by `attempt_id` and feed failed-outcome auto-disable.

## Verification

- Python learning-lane tests: 13 passed.
- Python compile: passed.
- Rust learning-lane tests: 7 passed.
- Rust cost-gate focused tests: 26 passed.

## Boundary

No DB write, no Bybit private/signed/trading call, no deploy/restart, no runtime config change, no risk/auth/order mutation, no main cost-gate relaxation.

Next step is operator-reviewed Rust hot-path wiring plus fill-backed outcome labels, not global cost-gate lowering.
