# 2026-06-22 Cost Gate Data-Flow Packet Refresh Cron

## Summary

v413 makes the Cost Gate learning lane refresh its own data-flow monitor and profit-learning decision packet. This closes the v412 gap where the side-cell was reviewable but the decision packet still said `DATA_FLOW_MONITOR_REQUIRED`.

This is still not a Cost Gate lowering request. It makes the autonomous learning loop more durable: it now records whether demo data is flowing, whether Cost Gate rejects are recorded, whether rejected signals are silently lost, and whether blocked side-cells are ready for operator review.

## Source Changes

- `helper_scripts/cron/cost_gate_learning_lane_cron.sh` now refreshes `demo_data_flow_monitor_latest.json` and `profit_learning_decision_packet_latest.json` as fail-soft artifact stages.
- Cron status lines now include `data_flow_monitor_rc`, `decision_packet_rc`, artifact hashes, data-flow status/reason/key counts, decision-packet status/reason/next actions, `decision_packet_silent_drop_risk`, and `decision_packet_data_flow_status`.
- `helper_scripts/research/cost_gate_learning_lane/decision_packet.py` now treats missing optional artifact paths as missing inputs instead of raising `FileNotFoundError`.
- Focused regression covers the missing sealed-horizon evidence path so runtime absence produces a fail-closed packet instead of a cron failure.

## Runtime Evidence

Linux preinstall-only smoke first exposed the missing optional sealed-evidence bug, then passed after source fix `15813333`.

Latest passing Cost Gate cron smoke:

- status timestamp: `2026-06-22T17:19:13Z`
- data-flow status: `DEMO_ORDER_FLOW_PRESENT_NO_FILLS`
- `broad_candidate_or_reject_rows=236007`
- `broad_cost_gate_rejects=58968`
- `broad_orders=3`
- `broad_fills=0`
- next action: `diagnose_order_to_fill_gap_before_cost_gate_changes`
- decision packet: `OPERATOR_REVIEW_DEMO_PROBE_CANDIDATES`
- decision reason: `blocked_signal_outcomes_clear_review_thresholds`
- `silent_drop_risk=false`
- sealed-horizon learning evidence available: `false`
- order authority granted: `false`

Latest alpha smoke:

- generated: `2026-06-22T17:19:57.176636+00:00`
- schema: `alpha_discovery_runtime_killboard_v8`
- runtime source: `SYNCED_CLEAN`
- worklist: `OPERATOR_GATED_LEARNING_READY`
- top task: `operator_probe_review`
- objective: `operator_review_multi_horizon_blocked_signal_side_cell_before_bounded_demo_probe`
- decision packet status: `OPERATOR_REVIEW_DEMO_PROBE_CANDIDATES`
- data-flow status: `DEMO_ORDER_FLOW_PRESENT_NO_FILLS`
- silent-drop risk: `false`
- top side-cell: `ma_crossover|ETHUSDT|Sell`
- candidate horizons: `[15,30,60,120,240]`
- best horizon: `120`

## PM Read

The system is not silent-dropping new Cost Gate rejects at the evidence layer: rejects are recorded and the learning path can see them. The current operational blocker is different: demo order flow exists but fills are absent, so any move toward profitability must diagnose order-to-fill/execution realism before changing Cost Gate thresholds.

The profitable path remains bounded and evidence-driven:

- keep the global Cost Gate intact;
- review the multi-horizon blocked side-cell as a bounded demo probe candidate;
- require explicit operator authorization before any probe authority;
- require matched-control result review and execution-realism review before any Cost Gate change.

## Verification

- Mac: `bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh` passed.
- Mac: decision-packet focused pytest `7 passed`.
- Mac: cron static pytest `13 passed`.
- Mac: py_compile and `git diff --check` passed.
- Source commits: `8550f0f3905261dcd11293f55afbefbd0f732315`, `15813333f4ec99c179b67ce254db89a6df587a11`, both pushed with `[skip ci]`.
- Linux: source fast-forwarded to `15813333`.
- Linux: `bash -n` passed.
- Linux: decision-packet focused pytest `7 passed`.
- Linux: cron static pytest `13 passed`.
- Linux: py_compile and `git diff --check` passed.
- Linux: Cost Gate cron preinstall-only smoke passed.
- Linux: alpha cron artifact-only smoke passed.

## Boundary

Source/test/docs + Linux source sync + read-only PG SELECT through existing artifact scripts + `/tmp/openclaw` artifact-only refresh/smoke only. No CI, no PG write/schema migration, no Bybit private/signed/trading call, no deploy/rebuild/restart, no crontab install, no writer/env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, no promotion proof.
