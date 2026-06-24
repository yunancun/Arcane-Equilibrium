# False-Negative Bounded Preflight Cron Bridge

Date: 2026-06-24
PM status: `DONE_WITH_CONCERNS`
Source checkpoint: `744d51366d9baf8dfbf05186fe4d6bc7e8cf8a7c`
Runtime source observed read-only: Linux `trade-core` `/home/ncyu/BybitOpenClaw/srv` at `c88deea7ead57a6e7f7b8d06cba8f7f235ad6a92`

## Session Loop State

- `active_blocker_id`: `P0-BOUNDED-PROBE-AUTHORIZATION`
- `blocker_goal`: connect exactly one selected false-negative candidate path to bounded Demo authorization review surfaces without granting authority.
- `profit_relevance`: high. The selected candidate remains `grid_trading|AVAXUSDT|Sell`; prior candidate packet reported 48/48 positive 60m after-cost outcomes, avg net about `73.55bps`, but it still lacks candidate-matched Demo fill/control proof.
- `completed_blockers`: `P0-PROFIT-EVIDENCE-QUALITY`, `P0-PROFIT-CANDIDATE-SELECTION`
- `blocked_blockers`: none newly closed; active blocker remains review/authority-gated.
- `previous_report_paths`: `2026-06-24--profit_evidence_cleanup_and_candidate_selection.md`, `2026-06-24--false_negative_bounded_probe_preflight_bridge.md`
- `source_head`: `1faddc37` before this source work; `744d5136` after source/test commit.
- `runtime_timestamp`: `2026-06-24T07:26:11+02:00`
- `pg_snapshot_timestamp`: `2026-06-24 07:26:47.30496+02`
- `artifact_mtimes`: false-negative candidate/review latest `1782275408`; sealed preflight latest `1782278521`; bounded authorization latest `1782278103`; profitability scorecard latest `1782278103`
- `operator_action_required`: candidate-specific bounded probe/order authority remains required before any order path; broad Demo API permission is not live/mainnet authority and is not a typed candidate-specific authorization object.
- `new_evidence_delta_required`: source/runtime/artifact/operator delta for active blocker.
- `new_evidence_delta_found`: yes. Source advanced after v458 and runtime artifacts showed the bounded chain still falling back to sealed BTC path instead of selected false-negative AVAX path.
- `acceptance_criteria`: source-only bridge creates canonical false-negative preflight latest artifact, uses it as active bounded preflight source, keeps no-authority/defer semantics, and tests cover fail-closed behavior.
- `next_blocker_id`: `P0-BOUNDED-PROBE-AUTHORIZATION`

## Anti-Repeat Decision

Decision: `supplied_evidence_snapshot_delta_allows_active_blocker_progress`

Reason: the active blocker was not repeated as another read-only audit. The new source delta made a concrete source-only fix possible: false-negative bounded preflight had a helper, but the recurring cron/review chain still defaulted back to sealed-horizon BTC artifacts.

## Action Taken

Implemented and committed source/test bridge:

- `cost_gate_learning_lane_cron.sh` now refreshes:
  - `learning_ssot_decision_latest.{json,md}`
  - `autonomous_parameter_proposal_latest.{json,md}`
  - `false_negative_bounded_probe_preflight_latest.{json,md}`
- The Cost Gate bounded review chain now uses `BOUNDED_PROBE_PREFLIGHT_SOURCE_JSON`, defaulting to the false-negative bounded preflight latest artifact.
- `alpha_discovery_throughput_cron.sh` prefers false-negative bounded preflight latest when present and falls back to sealed-horizon preflight when absent.
- `profitability_path_scorecard.py` accepts `--bounded-probe-preflight-json` and emits generic `bounded_probe_preflight_*` closure fields while preserving legacy sealed-horizon fields.

Authority boundaries preserved:

- No global Cost Gate lowering.
- No live/mainnet promotion.
- No active probe/order authority.
- No PG write/schema migration.
- No Bybit order/cancel/modify.
- No crontab edit, service restart, runtime deploy, or Rust writer enablement.
- Bounded operator authorization wrapper still uses `--decision defer` in cron and supplies no operator id, authorization id, or typed confirm.

## Verification

Passed locally:

- `bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh`
- `bash -n helper_scripts/cron/alpha_discovery_throughput_cron.sh`
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py`
- cron static: `17 passed`
- profitability scorecard: `18 passed`
- bounded Cost Gate helper suite: `142 passed`
- alpha runtime: `80 passed`
- alpha learning worklist: `10 passed`
- `git diff --check`

QA/E4 subagent review found no blocking findings. Residual concerns:

- If the false-negative bounded preflight latest artifact is missing, the Cost Gate chain fails closed but old latest artifacts can remain noisy until refreshed.
- Alpha cron fallback to sealed-horizon preflight preserves old behavior; it is not a strict false-negative-only mode.
- Runtime source remains `c88deea7`; this source bridge is not runtime-proven until synced/refreshed in the runtime environment.

## Aggressive Profit Hypotheses

1. False-negative AVAX bounded maker probe path.
   - Why it might make money: selected candidate has strong blocked-outcome after-cost cushion and perfect observed positive sample in the candidate packet.
   - Fastest safe test: source-only/runtime artifact refresh to produce the AVAX false-negative preflight latest, then candidate-specific review packet; no orders until authorization object exists.
   - Required data: candidate-matched Demo fills, fees/slippage, order intent/order-state lineage, L1 placement context, matched blocked controls.
   - Failure condition: unattributed fills, no candidate-matched fills, avg realized net <= 0 after fees/slippage, or matched controls show the apparent edge is not capturable.
   - Authority required: candidate-specific bounded Demo authorization only; no live/mainnet.
   - Max safe next action: runtime source sync plus artifact-only cron refresh if operator accepts runtime mutation.
   - Scores: expected_net_pnl_upside 5, evidence_strength 3, execution_realism 2, cost_after_fees 4, time_to_test 3, risk_to_account 2, risk_to_governance 2, autonomy_value 5.

2. Maker near-touch placement for false-negative Cost Gate cells.
   - Why it might make money: previous shadow placement evidence showed large touchability improvement versus deep passive no-touch behavior, while preserving maker intent.
   - Fastest safe test: use the false-negative preflight source through touchability/placement/shadow impact only; compare candidate-matched near-touch shadow limits against future BBO crosses.
   - Required data: fresh BBO, tick size, spread, post-only reject/cross outcomes, order-to-fill audit, candidate key alignment.
   - Failure condition: shadow would skip all orders, become taker-like, exceed passive gap, or only improves non-candidate samples.
   - Authority required: none for shadow; separate bounded Demo authority for actual order attempts.
   - Max safe next action: artifact-only shadow placement refresh after runtime source sync.
   - Scores: expected_net_pnl_upside 4, evidence_strength 3, execution_realism 3, cost_after_fees 4, time_to_test 4, risk_to_account 1, risk_to_governance 1, autonomy_value 4.

3. Current-fee MM repeat-window path.
   - Why it might make money: current-fee-positive MM cells exist, but only in limited windows; repeated independent windows could create a lower-friction alpha path than Cost Gate false-negative probing.
   - Fastest safe test: accumulate/replay independent windows for the same candidate key and require OOS/walk-forward plus maker execution-realism before any probe.
   - Required data: fresh fill_sim windows, recorder MM verdict, current fee tier, maker/taker fee split, per-symbol queue/fill-only evidence.
   - Failure condition: single-window positive disappears, net after current fees <= 0, or maker execution realism cannot be matched.
   - Authority required: none for replay/history; bounded Demo only if repeat/OOS gates pass.
   - Max safe next action: source/artifact-only repeat-window refresh.
   - Scores: expected_net_pnl_upside 3, evidence_strength 2, execution_realism 2, cost_after_fees 3, time_to_test 3, risk_to_account 1, risk_to_governance 1, autonomy_value 4.

## Status Transition

`DONE_WITH_CONCERNS`

Why not repeating current blocker: the blocker was advanced by a concrete source-only bridge and verified. Re-running the same read-only audit would not add evidence. The remaining work is runtime application / exact candidate-specific bounded authorization / outcomes, not another broad audit.
