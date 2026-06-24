# Candidate-Matched Touchability Gate

Date: 2026-06-24
PM status: `DONE_WITH_CONCERNS`
Runtime source checked: Linux `trade-core` `/home/ncyu/BybitOpenClaw/srv` at `2dd54a37`
Source change branch: `main`

## Session Loop State

- `active_blocker_id`: `P1-RUNTIME-HEALTH-HYGIENE`
- `blocker_goal`: fix the source-only false-ready in the bounded probe review chain so Demo evidence remains candidate-matched, reconstructable, and later portable to live controls.
- `profit_relevance`: high. The selected false-negative path is still `grid_trading|AVAXUSDT|Sell`; profitability cannot be proven or safely probed if unrelated fills can satisfy the touchability gate.
- `completed_blockers`: `P0-PROFIT-EVIDENCE-QUALITY`, `P0-PROFIT-CANDIDATE-SELECTION`, `P1-LEARNING-LOOP-CLOSURE`, `P1-AUTONOMOUS-PARAMETER-PROPOSAL`
- `blocked_blockers`: `P0-BOUNDED-PROBE-AUTHORIZATION`, `P0-PROFIT-OUTCOME-REVIEW`
- `previous_report_paths`: `2026-06-24--false_negative_runtime_preflight_approval_checkpoint.md`
- `source_head`: local/origin `2dd54a37` before this source fix.
- `runtime_timestamp`: `2026-06-24T08:19:03+02:00`
- `pg_snapshot_timestamp`: `2026-06-24 08:19:03.435815+02` read-only timestamp snapshot.
- `artifact_mtimes`: false-negative preflight `1782281288.965555`; runtime order-to-fill audit `1782281075`; touchability/placement latest from old source `1782281704.*`.
- `operator_action_required`: none for this source-only fix. Demo authorization was not converted into order/probe authority.
- `new_evidence_delta_required`: source-only progress scope `false_negative_touchability_candidate_match_gate_v1`.
- `new_evidence_delta_found`: yes. Runtime artifact smoke showed aggregate `FILL_FLOW_PRESENT` contained 4 non-candidate fills, 0 candidate-matched orders/fills for `grid_trading|AVAXUSDT|Sell`.
- `acceptance_criteria`: aggregate fills cannot satisfy touchability unless `strategy_name + symbol + side` match the active candidate; promotion-proof inputs are rejected; placement and authorization remain no-authority.
- `next_blocker_id`: `P0-BOUNDED-PROBE-AUTHORIZATION` once the source fix is synced and a defer-only authorization packet is refreshed.

## Anti-Repeat Decision

Decision: `source_only_progress_allowed_for_active_blocker`

Reason: this was not another broad audit or another “is demo running” check. The prior runtime checkpoint exposed a concrete false-ready: aggregate `FILL_FLOW_PRESENT` moved touchability to ready even though the selected candidate had no matched fills. That is a source-only blocker that can be fixed without Bybit, PG write, crontab, service, or authority mutation.

## Action Taken

- Tightened `bounded_probe_touchability_preflight.py`:
  - candidate matching now requires `strategy_name`, `symbol`, and `side`;
  - aggregate `FILL_FLOW_PRESENT` becomes `TOUCHABILITY_GATE_READY_FOR_OPERATOR_REVIEW` only when candidate-matched fill evidence exists;
  - non-candidate fills route to `CANDIDATE_TOUCHABILITY_DATA_REQUIRED` or `TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE`;
  - candidate/non-candidate fill counts use upstream `fill_count` totals;
  - `promotion_proof=true` is rejected as an authority-boundary violation.
- Tightened `bounded_probe_placement_repair_plan.py`:
  - `CANDIDATE_TOUCHABILITY_DATA_REQUIRED` passes through as blocking;
  - `promotion_proof=true` is rejected.
- Added regression tests for:
  - the current AVAX false-negative mismatch;
  - same symbol/side but wrong strategy;
  - missing candidate strategy fail-closed;
  - candidate multi-fill count accounting;
  - promotion-proof boundary rejection;
  - placement passthrough blocker.

## Runtime Artifact Smoke

Using copied runtime artifacts under `/tmp/openclaw_candidate_touchability_check`:

- current order audit: `FILL_FLOW_PRESENT`, reviewed orders `39`, fill rows `4`.
- filled rows: `SOLUSDT Sell risk_close`, `ETHUSDT Sell risk_close`, `XRPUSDT Sell risk_close`, `XRPUSDT Buy flash_dip_buy`.
- selected candidate: `grid_trading|AVAXUSDT|Sell`.
- candidate-matched orders: `0`.
- candidate-matched fills: `0`.
- non-candidate fills: `4`.
- new touchability status: `TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE`.
- new placement status: `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`.
- defer-only authorization packet: `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, `operator_authorization=null`, `operator_authorization_object_emitted=false`, no active runtime probe/order authority.

## Verification

- PA/E2/E4 read-only review completed. E2/E4 concerns on strategy degradation, `promotion_proof`, and fill-count accounting were fixed and covered by tests.
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_touchability_preflight.py helper_scripts/research/tests/test_cost_gate_bounded_probe_placement_repair_plan.py`: `18 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_alpha_discovery_throughput.py`: `106 passed`
- `PYTHONPATH=. python3 -m pytest -q helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py`: `14 passed`
- Adjacent bounded suite: `27 passed`
- `py_compile`: passed
- `git diff --check`: passed

## Constraints Checked

- No global Cost Gate lowering.
- No live/mainnet promotion.
- No probe/order authority object emitted.
- No Bybit private/signed/trading call.
- No PG write/schema migration.
- No crontab edit.
- No service restart/deploy/rebuild.
- No Rust writer enablement.
- No promotion proof.
- Unattributed or non-candidate fills are excluded from proof and bounded-probe touchability readiness.

## Aggressive Profit Hypotheses

1. Candidate-matched near-touch repair for `grid_trading|AVAXUSDT|Sell`
   - why it might make money: the false-negative replay edge is large after current cost assumptions, but current Demo order flow has no candidate-matched touch/fill evidence.
   - fastest safe test: defer-only authorization packet plus bounded near-touch-or-skip review; no order until a structured authorization object exists.
   - required data: candidate-matched order rows, fill/fee/slippage lineage, matched blocked controls.
   - failure condition: candidate-matched fill edge after fees/slippage fails or execution realism shows edge not captured.
   - authority required: explicit bounded Demo authorization object; no live.
   - max safe next action: refresh no-authority runtime artifacts after source sync.
   - score: upside high, evidence medium, execution realism medium, cost after fees unknown, time to test short, account risk low under Demo cap, governance risk low after this gate, autonomy value high.
2. Same-symbol wrong-strategy contamination audit for future candidates
   - why it might make money: prevents learning from falsely accepting noisy non-candidate fills, preserving demo budget for real edge.
   - fastest safe test: source-only tests over false-negative and sealed-horizon candidates.
   - required data: order strategy_name/symbol/side/fill_count rows.
   - failure condition: no contamination surfaces in recurring artifacts.
   - authority required: none.
   - max safe next action: add candidate identity checks to downstream result review if gaps appear.
   - score: upside medium, evidence strong, execution realism high, cost after fees neutral, time to test short, account risk none, governance risk low, autonomy value high.
3. Maker microstructure edge capture for bounded probes
   - why it might make money: near-touch post-only placement can preserve maker economics while producing fill-backed evidence.
   - fastest safe test: shadow placement plus future bounded Demo attempts only after authorization.
   - required data: BBO age, tick/qty step, candidate-matched fills, maker/taker fee, markout.
   - failure condition: fills require crossing/taker behavior or maker queue loses edge after fees.
   - authority required: bounded Demo authorization only.
   - max safe next action: artifact-only scorecard refresh and review packet.
   - score: upside medium-high, evidence medium, execution realism medium, cost after fees critical, time to test short after auth, account risk low Demo-only, governance risk low, autonomy value high.

## Status

`DONE_WITH_CONCERNS`: source-only gate is fixed and verified locally. Runtime latest artifacts still need a source sync / artifact-only refresh to replace the previous false-ready latest files, but no runtime/order authority was required or used in this step.
