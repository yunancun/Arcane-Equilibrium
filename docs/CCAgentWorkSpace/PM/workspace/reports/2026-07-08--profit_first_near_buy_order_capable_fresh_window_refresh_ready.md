# PM Report - NEAR Buy Order-Capable Fresh Window Refresh Request

Status: `READY_FOR_PM_E3_DISPATCH`

Active blocker: `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE`

## Current Machine Truth

- Three-way source sync was completed first: Mac `HEAD`, Mac `origin/main`, GitHub `main`, Linux `HEAD`, and Linux `origin/main` all matched `c66338e8b733acb52fc44160b55fb8e34105ecd6`; Linux worktree was clean.
- Current dynamic candidate remains `ma_crossover|NEARUSDT|Buy` from latest runtime artifacts, with `avg_net_bps=64.983` and current `outcome_count=5058`.
- Runtime canonical soak plan was materialized under the approved plan-materialization scope:
  - canonical path: `/home/ncyu/BybitOpenClaw/var/openclaw/cost_gate_learning_lane/bounded_demo_probe_soak_plan.json`
  - new sha256: `a296365eb03086b1e28595cc793c333068f5fde750e994232ad8563e6e36d32a`
  - materialization record: `/home/ncyu/BybitOpenClaw/var/openclaw/cost_gate_learning_lane/bounded_demo_probe_soak_plan_materialization_20260708T223909Z.json`
  - materialization record sha256: `a71b9fc42277e77414268ec052b34e32153a024fd8ffa8f058d6f5ddbc50e73a`
- No Bybit call, Decision Lease, order/probe/cancel/modify, private endpoint, PG/DB write, service/env/crontab mutation, Cost Gate lowering, live/mainnet action, or proof/promotion claim was performed after materialization.

## Gate Refresh Result

Generated current-head order-capable pre-execution inputs on Linux:

| Artifact | Status | SHA256 |
|---|---|---:|
| `/tmp/openclaw_near_order_capable_after_plan_materialization_20260708T2250Z_c66338e8/outputs/bounded_probe_active_order_wiring_contract_ready.json` | `ACTIVE_ORDER_WIRING_CONTRACT_READY_FOR_E3_BB_REVIEW` | `cf2c9ff29d29f8f251759f2fc0cbd37b1c7a9ef63959956048e8d7ec1babc6e0` |
| `/tmp/openclaw_near_order_capable_after_plan_materialization_20260708T2250Z_c66338e8/outputs/current_candidate_order_fill_evidence_scan_strict.json` | `NO_CANDIDATE_MATCHED_ACTUAL_ORDER_FILL_EVIDENCE` | `ca4bf9cb4188bf8c31fba919cc49ca6d6fd426c521afd5d7a78444359ff3d88c` |
| `/tmp/openclaw_near_order_capable_after_plan_materialization_20260708T2250Z_c66338e8/outputs/current_candidate_order_capable_demo_invoke_review_packet.json` | `CURRENT_CANDIDATE_ORDER_CAPABLE_DEMO_INVOKE_REVIEW_PACKET_BLOCKED_BY_LOSS_CONTROL` | `305774b2b1f0d3d3a3c4807e6f2739a47c395f0fb4c85b831e298f7a2081b40f` |

The order-capable review packet has exactly one loss-control blocker:

`renewed_active_bbo_manifest_stale_for_review_packet`

The stale manifest is `/home/ncyu/BybitOpenClaw/var/openclaw/profit_first_dynamic_candidate_same_window_final_gate_20260708T175744Z_08f7e957_noorder/renewed_active_bbo_execution_manifest.json`, sha `17a3a426f31cbff6c0180dfdd239ea6b0ef2b132df486dfc76764825963cf321`, generated at `2026-07-08T18:03:59.591986+00:00`. Its prior E3/BB approval was bound to checkpoint `08f7e957...`, so it cannot be reused at current checkpoint `c66338e8...`.

## Exact Request

PM generated a fresh current-head E3/BB exact-scope request:

- Request: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-08--profit_first_near_buy_order_capable_fresh_window_refresh_request.json`
- Manifest: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-08--profit_first_near_buy_order_capable_fresh_window_refresh_request.manifest.json`
- Request sha256: `ac1aa607efa5de0cf6d3834de8a09dc7a74748dddd88af4600d3372aaf8afaac`
- Manifest sha256: `dad9859e1b1511e5af682fb6e802c5aaaf09415e9a1fdc1e7397642a940a1108`

Requested scope is no-order only: E3/BB may review whether PM can refresh a new same-window Phase A/B no-order window at current source/runtime head using exactly three Demo public market-data GETs plus one short `TRADE_ENTRY` no-order Decision Lease acquire/release. The request does not authorize order/probe/private endpoint use.

## Stop

Stop condition: `READY_FOR_PM_E3_DISPATCH`.

Next safe action is E3/BB review of the exact request after this checkpoint is committed, pushed, and Linux source-only fast-forwarded. If source/runtime/candidate/auth/hash drift occurs before review consumption, rotate instead of using this packet.
