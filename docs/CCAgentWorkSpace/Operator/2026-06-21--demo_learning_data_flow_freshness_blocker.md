# Operator Note — Demo Learning Data-Flow Freshness Blocker

Date: 2026-06-21  
Status: source checkpoint only; no runtime change performed

## What Changed

Demo learning evidence now checks whether the latest learning-data row is fresh,
not only whether the 24h lookback contains rows.

If candidate/reject/order-flow data is stale, future alpha killboards will show:

```text
demo_learning_data_flow_stale
```

with next trigger:

```text
restore_demo_data_flow_before_cost_gate_learning_activation
```

## Current Runtime Facts

At `2026-06-21T23:17:12+02:00`, demo/live_demo was again producing
decision/risk rows:

- 1h `decision_features=2496`
- 1h `risk_verdicts=2496`
- latest both `2026-06-21 23:15:59.991+02`

But it still produced no order evidence:

- 1h / 4h `intents=0`, `orders=0`, `fills=0`
- 24h `intents=3`, `orders=3`, `fills=0`
- 1h risk verdicts were all Cost Gate rejects

Runtime source is still old/dirty/behind, and runtime alpha artifact is still
old-schema, so this source checkpoint is not active on `trade-core` yet.

## Boundaries

This checkpoint did not lower Cost Gate, grant order authority, sync runtime
source, restart services, install cron, write PG, call Bybit private/signed
APIs, or create promotion proof.
