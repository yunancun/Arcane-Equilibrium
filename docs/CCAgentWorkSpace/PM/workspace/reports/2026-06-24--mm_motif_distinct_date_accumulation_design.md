# MM Motif Distinct-Date Accumulation Design

日期：2026-06-24  
Active blocker：`P1-MM-MOTIF-DISTINCT-DATE-ACCUMULATION-DESIGN`  
角色鏈：PM -> E1(PM-local) -> E2 -> E4 -> PM  
狀態：`DONE_WITH_CONCERNS`

## 結論

`mm_motif_amplification_packet_v1` now carries a machine-readable `distinct_date_accumulation_design`.

This closes the source-only design gap after `P1-MM-CURRENT-FEE-REPEAT-WINDOW`: current-fee exact-cell repeat and motif-level distinct-date accumulation are now both explicit evidence contracts. It still does not prove profit, does not lower Cost Gate, and does not grant bounded Demo, order, probe, or live authority.

## Session Loop State

```json
{
  "session_goal": "Profit-first Demo-learning Autonomy Improvement Loop + Aggressive Alpha Expansion Mode",
  "active_blocker_id": "P1-MM-MOTIF-DISTINCT-DATE-ACCUMULATION-DESIGN",
  "blocker_goal": "Turn current no-authority MM current-fee/motif evidence into a source-only distinct-date accumulation design contract.",
  "profit_relevance": "The MM path is one of the few fee-aware routes with plausible net-after-fee upside, but it needs repeat/distinct-date, OOS, maker-realism, and bounded Demo proof gates before any Cost Gate or live-applicable use.",
  "completed_blockers": [
    "P1-RUNTIME-HEALTH-HYGIENE-FINAL-SNAPSHOT",
    "P1-RUNTIME-HEALTH-HYGIENE-API-ENABLE",
    "P1-RUNTIME-SOURCE-SYNC-MM-MOTIF-ARTIFACT-REFRESH",
    "P1-MM-CURRENT-FEE-REPEAT-WINDOW",
    "P1-LEARNING-LOOP-CLOSURE",
    "P1-AUTONOMOUS-PARAMETER-PROPOSAL"
  ],
  "blocked_blockers": [
    "P0-BOUNDED-PROBE-AUTHORIZATION",
    "P0-PROFIT-OUTCOME-REVIEW"
  ],
  "previous_report_paths": [
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--runtime_health_hygiene_final_snapshot.md",
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--runtime_mm_motif_artifact_refresh.md",
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--mm_current_fee_repeat_window_design.md"
  ],
  "source_head": "local/origin 7a79b0566d4c4e3bf97073614822f8d4cde19d7f; runtime operational dd3088dbee3b70eaf02b28f1279d0d3694b0cc5f",
  "runtime_timestamp": "2026-06-24T15:48:52+02:00",
  "pg_snapshot_timestamp": "not required; no PG read/write",
  "artifact_mtimes": {
    "mm_current_fee_confirmation_latest": "1782308704",
    "mm_motif_amplification_latest": "1782308704",
    "bounded_probe_operator_authorization_latest": "1782308704",
    "bounded_probe_result_review_latest": "1782307811",
    "false_negative_candidate_friction_scorecard_latest": "1782307810"
  },
  "operator_action_required": false,
  "new_evidence_delta_required": "fresh MM current-fee/motif artifact mtime or source-only path not already completed",
  "new_evidence_delta_found": "MM current-fee/motif artifacts refreshed at 2026-06-24T13:45:04Z and still require repeat/distinct-date evidence",
  "acceptance_criteria": [
    "No global Cost Gate lowering",
    "No Bybit/PG/runtime mutation",
    "No probe/order/live authority",
    "No single-window MM positive promoted as proof",
    "Produce a machine-checkable source-only design/packet for distinct-date accumulation",
    "Tie failure conditions to exact motif identity, fees, train/holdout, OOS, maker realism, and artifact exclusions"
  ],
  "next_blocker_id": "P1-MM-MOTIF-DISTINCT-DATE-EVIDENCE-ACCUMULATION"
}
```

## Anti-Repeat Decision

Skipped:

- `P1-RUNTIME-HEALTH-HYGIENE-FINAL-SNAPSHOT`: already `DONE`.
- `P0-BOUNDED-PROBE-AUTHORIZATION`: latest packet refreshed but still has no exact `operator_authorization` object and no emitted authority object.
- `P0-PROFIT-OUTCOME-REVIEW`: latest result review remains `NO_PROBE_OUTCOMES_RECORDED`.
- `P1-MM-CURRENT-FEE-REPEAT-WINDOW`: already completed exact-cell repeat-window hardening; this blocker is motif-level distinct-date design, not the same scope.

Proceeded because runtime artifacts refreshed and the motif-level design contract was still missing.

## Fresh Runtime Evidence

Read-only runtime artifact summary at `2026-06-24T13:45:04Z`:

- `mm_current_fee_confirmation_latest`: `MM_CURRENT_FEE_CONFIRMATION_REQUIRES_REPEAT_WINDOW`
  - candidate：`edge_scorecard|per_symbol_primary_queue|SOXLUSDT|back|informed_skip|fill_only`
  - `candidate_net_bps=0.715`
  - `candidate_observed_independent_windows=1`
  - `same_candidate_independent_windows_remaining=1`
- `mm_motif_amplification_latest`: `MM_MOTIF_AMPLIFICATION_REQUIRES_DISTINCT_DATE_HISTORY`
  - top motif：`low_friction_motif|spread_combo|recent_trade_imbalance`
  - `top_distinct_dates_remaining=2`
  - `top_frontier_candidate_count=4`
  - `top_frontier_gap_to_current_fee_bps=2.608`
  - `top_required_uplift_multiple=2.8736`
- `bounded_probe_operator_authorization_latest`: `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, `operator_authorization_object_emitted=false`
- `bounded_probe_result_review_latest`: `NO_PROBE_OUTCOMES_RECORDED`

## Source Changes

Changed:

- `helper_scripts/research/alpha_discovery_throughput/mm_motif_amplification.py`
- `helper_scripts/research/tests/test_mm_motif_amplification.py`
- `helper_scripts/SCRIPT_INDEX.md`
- `TODO.md`
- `docs/CLAUDE_CHANGELOG.md`

New packet fields:

- `distinct_date_accumulation_design`
- `summary.distinct_date_accumulation_design_status`
- `summary.distinct_date_max_safe_next_action`
- `answers.distinct_date_accumulation_design_present`
- `answers.distinct_date_accumulation_ready_for_review`
- `answers.motif_current_fee_candidate_ready_for_review`
- `answers.motif_current_fee_proven=false`

The design includes:

- fastest safe test
- required data
- failure conditions
- proof exclusions
- max safe next action
- no-authority / no-proof fields

## Review Chain

- PA skipped: existing packet design and previous current-fee repeat contract made design scope narrow.
- E1: PM-local implementation to avoid parallel edit conflict in a two-file source/test patch.
- E2: `DONE_WITH_CONCERNS`
  - Concern 1: `distinct_date_accumulation_design_ready` could be misread while status is still `DISTINCT_DATE_ACCUMULATION_REQUIRED`.
  - Concern 2: markdown additions were not locked by tests.
- PM fix:
  - Renamed to `distinct_date_accumulation_design_present`.
  - Added `distinct_date_accumulation_ready_for_review`.
  - Added markdown assertions for section, fastest safe test, authority-required note, and proof exclusions.
- E4: PASS after focused and adjacent regression.

## Verification

PM-local:

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_mm_motif_amplification.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py helper_scripts/research/tests/test_mm_current_fee_confirmation.py`  
  Result: `110 passed`
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/mm_motif_amplification.py helper_scripts/research/tests/test_mm_motif_amplification.py`  
  Result: passed
- `git diff --check`  
  Result: passed

E4:

- Focused MM motif test repeated: `3 passed`
- Adjacent alpha/worklist/current-fee regression repeated: `107 passed`
- py_compile: passed
- `git diff --check`: passed

Runtime-copied local smoke:

- source artifact copied from `trade-core:/tmp/openclaw/research/fillsim/fillsim_history_scorecard.json`
- output：`/tmp/openclaw_mm_motif_design_smoke_20260624T135222Z/mm_motif_amplification_design.json`
- status：`MM_MOTIF_AMPLIFICATION_REQUIRES_DISTINCT_DATE_HISTORY`
- design status：`DISTINCT_DATE_ACCUMULATION_REQUIRED`
- max safe next action：`accumulate_distinct_window_history_for_same_low_friction_motif`
- top motif：`low_friction_motif|spread_combo|recent_trade_imbalance`
- dates remaining：`2`
- gap：`2.608`
- proof/authority：false

## Aggressive Profit Hypotheses

### 1. Same-motif distinct-date accumulation

- `why_it_might_make_money`：the repeated spread + recent-trade-imbalance motif may represent a stable maker-side microstructure condition; the current frontier gap is specific (`2.608bps`) rather than undefined.
- `fastest_safe_test`：wait for next valid fill_sim history refresh or run isolated read-only replay preserving the same motif axes.
- `required_data`：fresh L1, fill_sim history window summaries, motif axes, train/holdout sample gates, current maker fees.
- `failure_condition`：motif does not repeat on distinct dates, train-only uplift overfits, holdout sample gate collapses, or min gross remains below fees.
- `authority_required`：none for source-only research/replay; future bounded Demo requires candidate-scoped review.
- `max_safe_next_action`：accumulate distinct-window history for the same motif.
- scoring：expected_net_pnl_upside 4/5, evidence_strength 2/5, execution_realism 2/5, cost_after_fees 2/5, time_to_test 3/5, risk_to_account 1/5, risk_to_governance 1/5, autonomy_value 4/5.

### 2. Exact SOXLUSDT current-fee cell repeat

- `why_it_might_make_money`：one exact cell is already `+0.715bps` after current maker fees.
- `fastest_safe_test`：same-candidate independent-window accumulation/replay.
- `required_data`：exact candidate key, non-empty fresh L1, history window summaries, maker fee round trip.
- `failure_condition`：no exact-key repeat, malformed window summaries, or maker realism fails.
- `authority_required`：none for research; no bounded Demo authority until review.
- `max_safe_next_action`：read-only repeat-window evidence accumulation.
- scoring：expected_net_pnl_upside 3/5, evidence_strength 3/5, execution_realism 2/5, cost_after_fees 3/5, time_to_test 4/5, risk_to_account 1/5, risk_to_governance 1/5, autonomy_value 4/5.

### 3. Fee-tier / maker-ratio route as amplifier, not proof substitute

- `why_it_might_make_money`：the motif gap is only a few bps; reducing all-in maker cost or increasing maker capture ratio could turn marginal current-fee candidates into viable Demo probes.
- `fastest_safe_test`：source-only sensitivity packet using existing fee schedule and observed maker fill/adverse-selection data.
- `required_data`：fee schedule, maker/taker mix, fill_sim adverse selection, volume/asset thresholds.
- `failure_condition`：fee tier cannot be reached at current scale, maker ratio cannot be improved, or gross edge still below cost.
- `authority_required`：none for analysis; operator/business decision required for any fee-tier route.
- `max_safe_next_action`：source-only fee sensitivity, no Cost Gate change.
- scoring：expected_net_pnl_upside 3/5, evidence_strength 2/5, execution_realism 3/5, cost_after_fees 3/5, time_to_test 3/5, risk_to_account 1/5, risk_to_governance 2/5, autonomy_value 3/5.

## Status Transition

- status：`DONE_WITH_CONCERNS`
- concern：runtime source is not synced to this source change, so canonical runtime latest artifacts do not yet include the new design fields. Sync/refresh is a separate runtime blocker.
- next_blocker_id：`P1-MM-MOTIF-DISTINCT-DATE-EVIDENCE-ACCUMULATION` or `P1-RUNTIME-SOURCE-SYNC-MM-MOTIF-DESIGN-ARTIFACT-REFRESH`
- why_not_repeating_current_blocker：source-level design is implemented and verified; repeating would not add evidence until runtime sync/artifact refresh or new independent date evidence appears.

## Boundary

Source/test/docs + local `/tmp` smoke only. No Bybit call/order/cancel/modify, no API POST, no PG query/write/schema migration, no crontab/service/unit/runtime mutation, no daemon-reload/restart/process signal, no global Cost Gate lowering, no probe/order/live authority, no Rust writer, and no promotion proof.
