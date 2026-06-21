# Cost-Gate Demo-Learning Lane Rust Policy Seam

## Summary

This batch moves the cost-gate demo-learning lane from a Python artifact/control-plane Adapter into a pure Rust policy seam inside `openclaw_engine`.

It does not wire the policy into order dispatch, does not lower the main cost gate, and does not grant order authority. Current selected side-cells still return `ORDER_AUTHORITY_NOT_GRANTED`.

## Why

The profitability problem is now partly an evidence-loop problem: blocked demo signals need bounded real demo probes and outcome labels, but that must happen inside the Rust trading-authority layer rather than through Python pretending an order was allowed.

This batch creates the Rust contract before any hot-path integration.

## Implementation

- Added `rust/openclaw_engine/src/demo_learning_lane.rs`.
- Added `rust/openclaw_engine/src/demo_learning_lane_tests.rs`.
- Exported `openclaw_engine::demo_learning_lane`.
- Mirrored schema `cost_gate_demo_learning_lane_adapter_v1` in Rust.
- Added pure policy functions for:
  - side-cell normalization
  - reject-reason normalization
  - JSON plan parsing
  - JSONL-style ledger row parsing
  - side-cell runtime state summary
  - fail-closed probe admission decisions
- Tightened Python planner/runtime adapter freshness so future artifact timestamps fail closed.
- Mirrored future plan timestamp rejection in Rust.

## Guardrails

- No IO, DB access, Bybit calls, order submission, or runtime config mutation.
- Demo/live_demo mode only.
- `main_cost_gate_adjustment` must remain `NONE`.
- Eligible reject reason is only `cost_gate_js_demo_negative_edge`.
- Event side-cell must be selected in the plan.
- Candidate guardrails must be intact.
- Ledger state enforces budget, cooldown, failed-outcome disablement, and manual side-cell disablement.
- Risk state must be `NORMAL`.
- Admission requires both `order_authority=DEMO_LEARNING_PROBE_GRANTED` and `adapter_enabled=true`.
- Current latest plan remains `order_authority=NOT_GRANTED`.

## Verification

- `cargo test -p openclaw_engine demo_learning_lane --lib` -> 7 passed.
- `cargo test -p openclaw_engine test_cost_gate_moderate --lib` -> 26 passed.
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` -> 11 passed.
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py helper_scripts/research/cost_gate_learning_lane/policy.py` -> passed.

## Boundary

Source/test/docs only. No PG write, schema migration, Bybit private/signed/trading call, engine/API rebuild or restart, credential/auth/risk/order/strategy/runtime mutation, signal proof, execution proof, or promotion proof.

## Next

Operator-reviewed Rust demo hot-path wiring, then durable runtime probe outcome labels and edge-estimator feedback. Keep the main cost gate unchanged until realized demo evidence proves a bounded side-cell rule deserves promotion review.
