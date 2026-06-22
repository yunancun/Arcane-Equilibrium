# Operator Note: Cost Gate Lane Order Touchability Auto Refresh

Date: 2026-06-22
Source commit: `5c61f0ce`

The Cost Gate learning lane can now refresh `demo_order_to_fill_gap_audit_v1` by itself before bounded touchability, placement repair, and shadow placement impact.

Operational meaning:

- The v419 manual step is no longer required for the lane to produce fresh order-touchability evidence.
- The stage is read-only PG SELECT and local artifact write only.
- It is controlled by `OPENCLAW_COST_GATE_REFRESH_ORDER_TOUCHABILITY_AUDIT` and defaults on.
- Status logs now expose order audit rc/status/counts/answers.
- Existing bounded probe artifacts still fail closed when input evidence is stale or missing.

Linux isolated smoke showed the wrapper generated fresh order audit and bounded chain in one run:

- Order audit: `PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH`
- Reviewed orders: 6
- Fill rows: 0
- Deep passive no-touch orders: 6
- Touchability preflight: `TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE`
- Placement repair plan: `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`
- Shadow placement impact: `SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH`

This does not authorize orders or probes. It only makes the learning system better at autonomously diagnosing that current Demo orders cannot produce fill-backed learning and that near-touch maker placement repair is required before any candidate-matched alpha proof can be collected.

No CI was run, no cron was installed, no env was changed, no service was restarted, no PG write occurred, no Bybit trading/private call was made, and no Cost Gate lowering, probe/order authority, or promotion proof was granted.
