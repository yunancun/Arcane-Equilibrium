# TODO Maintenance Compliance Compaction

Date: 2026-06-26 09:35 CEST

本輪按 operator 要求「跑完這輪先暫停一下，整理 TODO」。只做 source/doc-only TODO 維護與狀態對齊；沒有 runtime mutation、沒有 manual cron、沒有 PG、沒有 Bybit/API/order/cancel/modify、沒有 Cost Gate/cap/risk mutation、沒有 writer/adapter enablement、沒有 probe/order/live authority、沒有盈利或 proof 宣稱。

## Required Round Output

| Field | Value |
|---|---|
| `active_blocker_id` | `P1-TODO-MAINTENANCE-COMPLIANCE-COMPACTION` |
| `blocker_goal` | Bring `TODO.md` back to `docs/agents/todo-maintenance.md`: compact masthead, timestamped current facts, active queue, explicit gates, links to reports, and no passive next action. |
| `profit_relevance` | Prevents stale dispatch and repeated no-delta audits from consuming the profit loop; keeps aggressive alpha work routed only through reviewable, bounded, auditable checkpoints. |
| `constraints_checked` | No Cost Gate lowering, no live promotion, no Bybit order/cancel/modify, no PG query/write, no service restart/rebuild, no manual cron run, no `_latest` overwrite, no writer/adapter enablement, no cap/risk mutation, no order/probe/live authority, no proof claim. |
| `previous_evidence_checked` | `docs/agents/todo-maintenance.md`; TODO v560; latest PM report `2026-06-26--cap_envelope_proposal_runtime_sync.md`; runtime source/service snapshot; natural latest artifacts. |
| `new_evidence_delta_required` | Source-only TODO compliance gap plus any natural artifact delta needed to avoid stale current facts. |
| `new_evidence_delta_found` | TODO v560 had stale auth latest and a passive natural-refresh next action; runtime latest artifacts naturally refreshed: autonomous proposal now has cap-envelope evidence floor, bounded auth is AVAX-scoped but still defer/no-authority. |
| `anti_repeat_decision` | Do not rerun P0 authorization, runtime sync, or cap-envelope source work. This round is the operator-requested TODO maintenance checkpoint. |
| `action_taken_or_noop_reason` | Rewrote `TODO.md` to v561 active-queue shape; moved version narrative to changelog; recorded fresh artifact facts without treating them as authorization/proof. |
| `aggressive_profit_hypotheses` | See table below. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P1-AGGRESSIVE-ALPHA-LOW-PRICE-FALSE-NEGATIVE-EVIDENCE-FLOOR-RANKING-NO-ORDER` after operator resumes, unless a real P0 auth delta appears first. |
| `why_not_repeating_current_blocker` | TODO now fits the maintenance standard. Repeating without new TODO drift or stale evidence would be anti-repeat noise. |

## Fresh Evidence

- Session state: `/tmp/openclaw/session_loop_state_20260626T073551Z_todo_maintenance_compliance_compaction.json`
- Repo source head: `0685908f87dd6c91c28f8acbc0c2d1e1a1d79bb2`
- Runtime snapshot: `2026-06-26T07:35:35Z`; runtime head `dd22810ee41c353c1d214d9a3217862d7b2bac74`; API active, MainPID `2218842`.
- Autonomous proposal latest: mtime `2026-06-26T07:29:20Z`, sha `a71a5b06...`, `REVIEWABLE_PARAMETER_PROPOSAL_READY`, candidate `grid_trading|AVAXUSDT|Sell`, contains `cost_gate_cap_envelope_evidence_floor_v1`, `cap_envelope_mutation_allowed=false`.
- Bounded auth latest: mtime `2026-06-26T07:30:55Z`, sha `90322ebc...`, `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, candidate `grid_trading|AVAXUSDT|Sell`, defer/no authority.

## Aggressive Profit Hypotheses

| Hypothesis | Scores | Why it might make money | Fastest safe test | Required data | Failure condition | Authority required | Max safe next action |
|---|---|---|---|---|---|---|---|
| Current-cap low-price false-negative evidence floor | expected_net_pnl_upside Medium; evidence_strength Medium; execution_realism Medium; cost_after_fees Mixed; time_to_test Fast; risk_to_account None source-only; risk_to_governance Low; autonomy_value High | Lower-price false negatives may fit current cap without exposure mutation and preserve net edge after costs. | Source-only ranking against evidence-floor dimensions. | Cap-feasible screen, scorecard, spread/markout controls, lineage/proof exclusions. | Net cushion disappears after realistic costs or no repeat/OOS path. | Research only; bounded auth before order. | After pause/resume, run source-only ranking. |
| ETH Tier-1 cap envelope | expected_net_pnl_upside High; evidence_strength Low-Medium; execution_realism Low now; cost_after_fees modeled favorable; time_to_test Medium; risk_to_account None now/Medium if cap changes; risk_to_governance Medium; autonomy_value High | ETH remains high-upside if cap envelope can be justified with complete floor evidence and survival-safe sizing. | Review natural autonomous proposal evidence floor only; no cap/order mutation. | Candidate-matched controls, fees/slippage, BBO/metadata, cap staircase, portfolio risk, execution realism, regime labels. | Floor incomplete or cap rise weakens survival/risk envelope. | Operator/QC cap review plus PM -> E3 -> BB before order. | Research/proposal only. |
| AVAX scoped authorization admission | expected_net_pnl_upside High path-enabler; evidence_strength Medium-High; execution_realism blocked by auth; cost_after_fees favorable modeled; time_to_test Fast if valid auth appears; risk_to_account None now; risk_to_governance Medium; autonomy_value High | AVAX is current-cap feasible and still the selected bounded candidate. | Review only a real AVAX-scoped typed-confirm/standing-auth artifact delta. | Exact false-negative preflight approval, bounded auth object, fresh BBO, cap construction, fills/fees/slippage lineage. | No exact auth, stale candidate, or authority contamination. | Candidate-scoped auth plus E3/BB; no authority now. | Stop at authorization gate. |

## Status

`DONE_WITH_CONCERNS`.

Concern: natural artifact refresh is useful evidence that v559 is active, but it does not grant probe/order authority and does not prove profitability. Per operator request, pause after this round.
