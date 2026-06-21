# Operator Note — Demo Order-Flow Starvation Blocker

Date: 2026-06-21  
Status: source checkpoint only; no runtime change performed

## What Changed

Future demo-learning evidence will explicitly report when Cost Gate is producing
fresh rejects but demo still has no real order/fill evidence:

```text
COST_GATE_REJECT_WALL_NO_ORDER_FLOW_EVIDENCE
```

Alpha-discovery will surface that as:

```text
demo_cost_gate_reject_wall_no_order_flow_evidence
```

with next trigger:

```text
activate_cost_gate_learning_lane_then_operator_review_bounded_demo_probe
```

## Why

For development, rejected signals are useful but not enough. We need controlled
demo order/fill evidence to validate execution, slippage, and whether Cost Gate
is blocking profitable signals.

## Boundaries

This checkpoint did not lower Cost Gate, grant order authority, sync runtime
source, restart services, install cron, write PG, call Bybit private/signed
APIs, or create promotion proof.
