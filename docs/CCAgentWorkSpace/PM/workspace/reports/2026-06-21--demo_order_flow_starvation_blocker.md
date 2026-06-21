# Demo Order-Flow Starvation Blocker

Date: 2026-06-21  
Role: PM local implementation checkpoint  
Status: source/test/docs complete; runtime still unsynced

## Finding

After v352, demo-learning evidence can tell whether candidate/reject data is
fresh. The next missing operator-facing fact was narrower: fresh Cost Gate
rejects can still leave the system with zero real demo order/fill evidence.

That is exactly the current runtime shape from the latest read-only probe:

- demo/live_demo decision/risk rows resumed in the latest hour
- 1h and 4h intents/orders/fills are still zero
- 24h has only three orders and zero fills
- the latest 1h risk verdicts are all Cost Gate rejects

Counts alone showed this, but alpha-discovery did not expose it as its own
machine-readable blocker.

## Change

`demo_learning_evidence_audit.py` now emits an `order_flow_evidence` scorecard:

- `COST_GATE_REJECT_WALL_NO_ORDER_FLOW_EVIDENCE`
- `DEMO_ORDER_FLOW_PRESENT_NO_FILL_EVIDENCE`
- `DEMO_FILL_EVIDENCE_PRESENT`
- fallback no-order-flow states

The composite answers now include:

- `recent_order_flow_present`
- `recent_fill_evidence_present`
- `order_flow_evidence_starved`
- `candidate_or_reject_without_order_flow`

Alpha-discovery now promotes the fresh Cost Gate reject wall with zero order/fill
evidence to:

```text
primary_blocker = demo_cost_gate_reject_wall_no_order_flow_evidence
next_trigger = activate_cost_gate_learning_lane_then_operator_review_bounded_demo_probe
```

This is still a data/evidence blocker. It does not lower the main Cost Gate and
does not grant order authority.

## Verification

- `python3 -m pytest helper_scripts/db/audit/test_demo_learning_evidence_audit.py -q` -> `7 passed`
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> `43 passed`
- `python3 -m py_compile helper_scripts/db/audit/demo_learning_evidence_audit.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`

## Boundary

No runtime source sync, artifact refresh, crontab edit/install, env edit,
deploy/rebuild/restart, PG write/schema migration, Bybit private/signed/trading
call, credential/auth/risk/order/strategy mutation, order authority, Cost Gate
lowering, execution proof, or promotion proof.

## PM Read

This directly supports the profitability goal: if demo never produces orders or
fills, local measurements cannot calibrate execution, slippage, or whether Cost
Gate blocked a profitable signal. The next real runtime step remains
operator-approved source sync and activation of the bounded learning lane before
any bounded demo probe review.
