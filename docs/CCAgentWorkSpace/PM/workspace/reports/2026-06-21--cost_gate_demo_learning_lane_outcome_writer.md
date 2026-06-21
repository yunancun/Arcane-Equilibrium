# Cost-Gate Demo-Learning Lane Outcome Writer

## Summary

This batch adds the artifact-only outcome writer for the bounded cost-gate demo-learning lane.

It does not route orders, grant order authority, lower the main cost gate, connect to PG, call Bybit, or mutate runtime config.

## Why

The demo-learning lane needs a durable learning loop, not just an admission decision. A probe that is admitted must later become outcome evidence so the side-cell can either earn more exploration or auto-disable after poor realized markouts.

The current plan still has `order_authority=NOT_GRANTED`, so this is infrastructure for learning from future admitted probes, not active order routing.

## Implementation

- Added `helper_scripts/research/cost_gate_learning_lane/contract.py` for shared adapter constants.
- Added `helper_scripts/research/cost_gate_learning_lane/outcome_writer.py`.
- Extended `helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py` with:
  - `--record-outcomes`
  - `--price-observations`
  - `--outcome-horizon-minutes`
  - `--outcome-cost-bps`
  - `--max-entry-delay-ms`
- Split the outcome writer out of `runtime_adapter.py`; the adapter is now 685 lines, below the repo's 800-line review threshold.

## Outcome Contract

- Processes only `record_type=probe_admission_decision` rows whose decision is `ADMIT_DEMO_LEARNING_PROBE`.
- Uses `attempt_id` for idempotency.
- Waits until the configured horizon has matured.
- Uses event entry price when present, otherwise the first local observation at or after entry within the configured delay.
- Uses the first local observation at or after horizon exit.
- Computes side-aware gross bps and net bps after explicit cost.
- Emits `record_type=probe_outcome`, `outcome_source=market_markout_proxy`, and `promotion_evidence=false`.
- Feeds the existing failed-outcome auto-disable path in the runtime adapter.

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` -> 13 passed.
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py helper_scripts/research/cost_gate_learning_lane/outcome_writer.py helper_scripts/research/cost_gate_learning_lane/contract.py helper_scripts/research/cost_gate_learning_lane/policy.py` -> passed.
- `cargo test -p openclaw_engine demo_learning_lane --lib` -> 7 passed.
- `cargo test -p openclaw_engine test_cost_gate_moderate --lib` -> 26 passed.

## Boundary

Source/test/docs only. No PG write, schema migration, Bybit private/signed/trading call, engine/API rebuild or restart, credential/auth/risk/order/strategy/runtime mutation, signal proof, execution proof, or promotion proof.

## Next

Operator-reviewed Rust demo hot-path wiring, then a fill-backed runtime outcome writer and edge-estimator feedback. Keep the main cost gate unchanged until realized demo evidence proves a bounded side-cell rule deserves promotion review.
