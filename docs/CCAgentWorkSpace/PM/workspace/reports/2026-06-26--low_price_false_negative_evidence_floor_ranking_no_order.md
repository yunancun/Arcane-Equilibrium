# Low-Price False-Negative Evidence-Floor Ranking No-Order

Date: 2026-06-26 09:42 CEST

本輪把 low-price false-negative ranking 從人工表格變成 machine-checkable source-only helper。沒有 runtime mutation、沒有 manual cron、沒有 PG、沒有 Bybit/API/order/cancel/modify、沒有 Cost Gate/cap/risk mutation、沒有 writer/adapter enablement、沒有 probe/order/live authority、沒有盈利或 proof 宣稱。

## Required Round Output

| Field | Value |
|---|---|
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-LOW-PRICE-FALSE-NEGATIVE-EVIDENCE-FLOOR-RANKING-NO-ORDER` |
| `blocker_goal` | Rank current-cap false-negative candidates against evidence-floor dimensions without changing candidate selection, cap/risk, runtime, or authority. |
| `profit_relevance` | Finds the fastest current-cap path toward real risk-adjusted net PnL proof while excluding cap-infeasible, bad-BBO, thin-cushion, under-sampled, and proof-incomplete paths. |
| `constraints_checked` | No Cost Gate lowering, no live promotion, no Bybit order/cancel/modify, no PG query/write, no service restart/rebuild, no manual cron run, no `_latest` overwrite, no writer/adapter enablement, no cap/risk mutation, no order/probe/live authority, no proof claim. |
| `previous_evidence_checked` | v561 TODO; low-price filter/control reports; v559 proposal evidence-floor source patch; latest runtime scorecard/cap/proposal/auth artifacts. |
| `new_evidence_delta_required` | Fresh scorecard/proposal/auth artifact delta or active evidence-floor contract so this is not a repeat of the older low-price filter. |
| `new_evidence_delta_found` | Latest scorecard sha `7361c1dc...`; autonomous proposal has `cost_gate_cap_envelope_evidence_floor_v1`; auth remains AVAX defer/no-authority. |
| `anti_repeat_decision` | Proceeded because the new helper makes the ranking reproducible against new artifacts; do not rerun on the same artifacts. |
| `action_taken_or_noop_reason` | Added source-only ranking helper, tests, script index, local smoke, and TODO/report state. |
| `aggressive_profit_hypotheses` | See table below. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION` only if real candidate-scoped auth delta appears; otherwise `P1-AGGRESSIVE-ALPHA-EVIDENCE-FLOOR-GAP-CLOSURE-DESIGN-NO-ORDER`. |
| `why_not_repeating_current_blocker` | Ranking is now source-backed and smoke-tested; repeating without scorecard/cap/proposal/auth delta would add no evidence. |

## Source Change

Added:

- `helper_scripts/research/cost_gate_learning_lane/false_negative_evidence_floor_ranking.py`
- `helper_scripts/research/tests/test_cost_gate_false_negative_evidence_floor_ranking.py`

Updated:

- `helper_scripts/SCRIPT_INDEX.md`

The helper emits `cost_gate_false_negative_evidence_floor_ranking_v1`. It fail-closes on any Cost Gate lowering, cap/risk/runtime mutation, PG write, Bybit/order, probe/order/live authority, or promotion/proof signal.

## Runtime Artifact Smoke

Local no-order smoke copied runtime artifacts into `/tmp/openclaw/false_negative_evidence_floor_ranking_smoke_20260626T074233Z/` and ran the new helper.

Result:

- status: `FALSE_NEGATIVE_EVIDENCE_FLOOR_RANKING_READY_NO_AUTHORITY`
- leader: `grid_trading|AVAXUSDT|Sell`
- leader classification: `REVIEW_ONLY_LEADER_NOT_PROOF`
- ranked count: `10`
- floor satisfied count: `0`
- probe/order authority: `false/false`

Top classifications:

| Rank | Candidate | Classification | Key reason |
|---:|---|---|---|
| 1 | `grid_trading|AVAXUSDT|Sell` | `REVIEW_ONLY_LEADER_NOT_PROOF` | Passes current-cap/clean-BBO/sample/cushion prefilter; still lacks proof-level controls/fills/realism/regime/OOS. |
| 2 | `grid_trading|ETHUSDT|Buy` | `RESEARCH_ONLY_CAP_INFEASIBLE` | High modeled cushion but fails current cap and sample floor. |
| 3 | `grid_trading|XRPUSDT|Sell` | `REJECT_EVIDENCE_FLOOR_PREFILTER` | Cushion too thin. |
| 4 | `grid_trading|SUIUSDT|Sell` | `RESEARCH_CONTROL_SAMPLE_BELOW_FLOOR` | Clean current-cap control but sample below `30`. |
| 5 | `grid_trading|ETCUSDT|Sell` | `REJECT_BBO_OR_SPREAD_NOT_CLEAN` | Incomplete BBO. |

## Verification

```text
PYTHONPATH=helper_scripts/research python3 -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_false_negative_evidence_floor_ranking.py
5 passed

PYTHONPATH=helper_scripts/research python3 -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_false_negative_candidate_friction_scorecard.py \
  helper_scripts/research/tests/test_cost_gate_autonomous_parameter_proposal.py
14 passed

python3 -m py_compile \
  helper_scripts/research/cost_gate_learning_lane/false_negative_evidence_floor_ranking.py \
  helper_scripts/research/tests/test_cost_gate_false_negative_evidence_floor_ranking.py
PASS

git diff --check
PASS
```

## Aggressive Profit Hypotheses

| Hypothesis | Scores | Why it might make money | Fastest safe test | Required data | Failure condition | Authority required | Max safe next action |
|---|---|---|---|---|---|---|---|
| AVAX current-cap evidence-floor leader | expected_net_pnl_upside Medium-High; evidence_strength Medium; execution_realism Low until fills; cost_after_fees modeled favorable; time_to_test Fast after auth; risk_to_account None now; risk_to_governance Low; autonomy_value High | It passes current cap, clean BBO, sample `48`, 100% modeled net-positive, and 73.5511bps cushion. | Candidate-scoped auth delta, then E3/BB order-envelope review; until then only close evidence gaps. | Candidate-matched fills, controls, fees/slippage/maker-taker, fresh BBO, proof scan, execution realism, regime/OOS labels. | No auth, no matched fills, controls beat probe, or execution realism fails. | Candidate-scoped bounded auth plus PM->E3->BB before order. | Keep as review-only leader; no order. |
| SUI/FIL current-cap research controls | expected_net_pnl_upside Medium; evidence_strength Low-Medium; execution_realism Low; cost_after_fees thin; time_to_test Fast source-only; risk_to_account None; risk_to_governance Low; autonomy_value Medium | They test whether AVAX is symbol-specific or part of a broader low-price grid effect. | Source-only gap-closure design; do not count as AVAX proof. | Fresh scorecard/cap screen, controls, fee/slippage labels, regime/OOS. | Sample remains below floor or controls outperform AVAX. | Research only; no order authority. | Keep as controls. |
| ETH cap-envelope research path | expected_net_pnl_upside High; evidence_strength Low; execution_realism Low; cost_after_fees favorable modeled; time_to_test Medium; risk_to_account None now/Medium if cap changes; risk_to_governance Medium; autonomy_value High | ETH modeled edge is large but currently cap-infeasible; a future cap envelope could unlock upside if survival math is strong. | Separate cap-envelope floor review only. | Cap staircase, portfolio risk budget, fresh BBO, controls, sample/fill realism, OOS. | Cap rise weakens survival/risk or floor remains incomplete. | Operator/QC/E3/BB before any cap/order mutation. | Research/proposal only. |

## Status

`DONE_WITH_CONCERNS`.

Concern: AVAX is the best review-only leader, but `floor_satisfied_count=0`; no candidate has proof-grade evidence. P0 authorization remains blocked/no-repeat.
