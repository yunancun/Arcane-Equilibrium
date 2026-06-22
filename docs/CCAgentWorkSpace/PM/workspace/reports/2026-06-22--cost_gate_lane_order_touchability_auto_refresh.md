# Cost Gate Lane Order Touchability Auto Refresh

Date: 2026-06-22
Source commit: `5c61f0ce`

## Summary

v420 closes the manual artifact prerequisite exposed by v419.

`cost_gate_learning_lane_cron.sh` now refreshes the read-only Demo order-to-fill touchability audit before bounded probe touchability, placement repair, and shadow placement impact. The learning lane can now produce the evidence it needs to decide whether bounded Demo probes are touchable without a separate manual audit run.

## Engineering Change

- Added `OPENCLAW_COST_GATE_REFRESH_ORDER_TOUCHABILITY_AUDIT` default-on stage.
- Added order-audit knobs for engine modes, lookback, touch window, placement window, top limit, and deep-gap threshold.
- Writes dated and latest `demo_order_to_fill_gap` JSON/Markdown artifacts under `OPENCLAW_DATA_DIR`.
- Status JSON now records order-touchability rc, refresh flag, skip reason, artifact path, latest path, sha256/error, status/reason/next action, counts, and no-authority answers.
- Bounded touchability still consumes `ORDER_TOUCHABILITY_JSON`, but the wrapper refreshes it first when enabled.

## Runtime Smoke

Linux isolated artifact-only smoke used `/tmp/openclaw_cost_gate_order_touchability_smoke` and exited `0`.

Key status:

- `order_touchability_audit_rc=0`
- `order_touchability_audit_status=PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH`
- `reviewed_orders=6`
- `fill_rows=0`
- `deep_passive_no_touch_orders=6`
- `bounded_probe_touchability_preflight_status=TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE`
- `bounded_probe_placement_repair_plan_status=PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`
- `bounded_probe_shadow_placement_impact_status=SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH`
- `bounded_probe_shadow_placement_submit_count=6`
- `bounded_probe_shadow_placement_candidate_matched_order_count=0`
- `bounded_probe_shadow_placement_max_gap_reduction_bps=1522.1026`

## Canonical Runtime Proof

After source and docs sync, the same v420 path was run against canonical `/tmp/openclaw` with scorecard/data-flow/plan/decision refresh, materializer, and ledger appends disabled.

Latest canonical status line:

- `ts_utc=2026-06-22T19:16:18Z`
- `order_touchability_audit_rc=0`
- `order_touchability_audit_status=PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH`
- `reviewed_orders=6`
- `fill_rows=0`
- `deep_passive_no_touch_orders=6`
- `bounded_probe_touchability_preflight_status=TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE`
- `bounded_probe_placement_repair_plan_status=PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`
- `bounded_probe_shadow_placement_impact_status=SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH`
- `bounded_probe_shadow_placement_submit_count=6`
- `bounded_probe_shadow_placement_candidate_matched_order_count=0`

Canonical latest artifacts now have generated times `2026-06-22T19:16:16-17Z`.

Canonical alpha refresh then produced `alpha_discovery_runtime_killboard_v9` at `2026-06-22T19:16:38Z`, source `SYNCED_CLEAN` at `6a2d0fc6`, top task `bounded_probe_placement_repair`, next trigger `operator_review_mechanical_touchability_before_rust_patch`, and fresh shadow generated time `2026-06-22T19:16:17Z`.

## PM Read

This makes the autonomous learning loop materially deeper. The lane no longer has a shallow interface that says "refresh bounded probe review" while depending on an external, manual order-touchability artifact.

The system still has no Cost Gate/order/probe authority. It is now better at autonomously proving why it cannot learn from current Demo orders and what mechanical repair is needed before candidate-matched alpha evidence can exist.

## Verification

- Mac bash syntax passed.
- Mac py_compile passed.
- Mac cron static: `13 passed`.
- Mac order audit: `8 passed`.
- Mac bounded touchability/placement/shadow: `17 passed`.
- `git diff --check` passed.
- Source commit `5c61f0ce` pushed with `[skip ci]`.
- Linux source fast-forwarded clean to `5c61f0ce`.
- Linux bash syntax passed.
- Linux cron static: `13 passed`.
- Linux order audit: `8 passed`.
- Linux bounded touchability/placement/shadow: `17 passed`.
- Linux py_compile passed.
- Linux isolated artifact-only wrapper smoke passed.

## Boundary

Source/test/docs plus Linux source sync and read-only PG SELECT with isolated `/tmp` artifact writes only. No CI run, no PG write/schema migration, no Bybit private/signed/trading call, no deploy/rebuild/restart, no crontab install/env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, and no promotion proof.
