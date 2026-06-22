# Runtime Shadow Placement Artifact Refresh

Date: 2026-06-22
Runtime source: `5b25a5e1`

## Summary

After v418 source sync, the Linux runtime artifacts were refreshed without any authority change.

The result is concrete: Demo is still creating order data, but the current flow is not creating fill-backed learning data because the submitted limits are too deep to touch BBO. The profitable path is therefore not global Cost Gate lowering. It is bounded side-cell/horizon learning plus a near-touch maker placement repair that can create candidate-matched fills for review.

## Runtime Evidence

- `demo_order_to_fill_gap_audit_v1`: `PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH`
- Reviewed orders: 6
- Fill rows: 0
- PostOnly orders: 6
- Deep passive no-touch orders: 6
- BBO-touched-no-fill orders: 0
- Max best-touch gap: `1530.6074bp`

Fresh bounded artifacts:

- `bounded_probe_touchability_preflight_latest.json`: `TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE`
- `bounded_probe_placement_repair_plan_latest.json`: `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`
- `bounded_probe_shadow_placement_impact_latest.json`: `SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH`

Shadow placement result:

- Shadow submits: 6/6
- Shadow skips: 0
- Max repaired initial touch gap: `58.2092bp`
- Avg repaired initial touch gap: `17.0489bp`
- Max gap reduction: `1522.1026bp`
- Future BBO crosses repaired shadow limit: 4/6
- Candidate-matched order count: 0

## Alpha Loop Result

Manual artifact-only `alpha_discovery_throughput_cron.sh` refreshed `alpha_discovery_runtime_killboard_v9` at `2026-06-22T19:00:37Z`.

Top learning task:

- Task type: `bounded_probe_placement_repair`
- Objective: `make_bounded_demo_probe_orders_touchable_then_collect_candidate_matched_fill_lineage`
- Completion gate: `candidate_matched_near_touch_shadow_or_fill_lineage_recorded`
- Next trigger: `operator_review_mechanical_touchability_before_rust_patch`
- Engineering actionable: true
- Requires operator authorization: true
- Runtime mutation required: false

## PM Read

The system is not failing because it has no rejected-signal data. It has blocked-signal candidates and order evidence. It is failing to learn because the Demo orders are not touchable, so they cannot produce fills, fees, slippage, or execution-realism evidence.

The next profitable engineering step is to make bounded Demo probes touchable while preserving maker/post-only discipline:

1. Select side-cell/horizon candidates from blocked-signal net-cost cushion evidence.
2. Use fresh BBO and maker-side near-touch post-only limits.
3. Skip and record when the initial passive gap is wider than `75bp`.
4. Collect candidate-matched order-to-fill and fill/fee/slippage lineage.
5. Compare probe outcomes against matched blocked controls.
6. Run bounded result review and execution-realism review before any Cost Gate change.

## Boundary

Read-only PG SELECT plus `/tmp/openclaw` artifact writes and artifact-only alpha wrapper only. No CI run, no PG write/schema migration, no Bybit private/signed/trading call, no deploy/rebuild/restart, no crontab install/env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, and no promotion proof.
