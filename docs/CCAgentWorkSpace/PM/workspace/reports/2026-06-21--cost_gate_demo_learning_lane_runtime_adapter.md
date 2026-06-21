# Cost-Gate Demo-Learning Lane Runtime Adapter

## Summary

This batch adds the source-only runtime-control Adapter for the cost-gate demo-learning lane.

The Adapter consumes:

- `cost_gate_demo_learning_lane_plan_v1`
- one rejected demo signal event
- append-only JSONL probe ledger rows

It emits schema `cost_gate_demo_learning_lane_adapter_v1` with a fail-closed admission decision.

## Why

The prior scorecard and plan showed that demo is still accumulating cost-gate rejection evidence, but blocked side-cells did not yet have a runtime contract for probe attempts, outcomes, cooldown, budget exhaustion, or failed-outcome disablement.

The correct next step is not to lower the main cost gate globally. It is to add a bounded learning lane whose attempts and outcomes are auditable.

## Implementation

- Added `helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py`.
- Added `ORDER_AUTHORITY_GRANTED = DEMO_LEARNING_PROBE_GRANTED` as the future explicit authority string.
- Added `evaluate_probe_admission(...)`.
- Added JSONL ledger helpers:
  - `build_ledger_record(...)`
  - `append_jsonl_ledger(...)`
  - `read_jsonl_ledger(...)`
- Added side-cell runtime summary:
  - admitted attempts
  - remaining budget
  - cooldown state
  - completed probe outcomes
  - failed-outcome auto-disable

## Guardrails

- Only demo/live_demo events are eligible.
- Only `cost_gate_js_demo_negative_edge` is eligible.
- The event side-cell must be selected in the plan.
- Candidate guardrails must keep `main_cost_gate_adjustment=NONE`.
- Current latest plan still has `order_authority=NOT_GRANTED`, so matching events return `ORDER_AUTHORITY_NOT_GRANTED`.
- A future admit requires both `order_authority=DEMO_LEARNING_PROBE_GRANTED` and `adapter_enabled=True`.
- This Adapter does not submit orders, connect to PG, call Bybit, or mutate runtime state.

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` -> 9 passed.
- `python3 -m pytest helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` -> 15 passed.
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py helper_scripts/research/cost_gate_learning_lane/policy.py` -> passed.
- `cargo test -p openclaw_engine test_cost_gate_moderate --lib` from `srv/rust` -> 26 passed.

## Boundary

Source/test/docs only. No PG write, schema migration, Bybit private/signed/trading call, engine/API rebuild/restart, credential/auth/risk/order/strategy/runtime mutation, signal proof, execution proof, or promotion proof.

## Next

Wire this contract into the Rust demo hot path only after explicit operator authority. Then add durable runtime probe outcomes and feed realized labels back to the edge estimator.
