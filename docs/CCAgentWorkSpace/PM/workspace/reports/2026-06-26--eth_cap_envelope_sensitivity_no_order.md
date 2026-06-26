# ETH Cap Envelope Sensitivity No-Order

Date: 2026-06-26 09:04 CEST

本輪只做 source-only / read-only 決策整理：把 `grid_trading|ETHUSDT|Buy` 的可執行 cap 階梯量化清楚，並修正 TODO 狀態機。沒有 Bybit order/cancel/modify、沒有 PG write/query、沒有 runtime mutation、沒有 crontab/service 操作、沒有 Cost Gate/cap/risk mutation、沒有 probe/order/live authority。

## Required Round Output

| Field | Value |
|---|---|
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-ETH-CAP-ENVELOPE-SENSITIVITY-NO-ORDER` |
| `blocker_goal` | Quantify the executable ETH Buy cap staircase from existing no-order construction evidence and latest false-negative scorecard without mutating cap, risk, runtime, order, Cost Gate, or authority state. |
| `profit_relevance` | ETH Buy remains the highest modeled false-negative lead, but a future cap-envelope review needs exact discrete exposure tiers before it can decide whether upside justifies bounded risk. |
| `constraints_checked` | No Cost Gate lowering, no live promotion, no Bybit order/cancel/modify, no PG write/query, no runtime/env/crontab/service mutation, no Rust writer/adapter enablement, no cap/risk mutation, no probe/order/live authority, no profit/proof claim. |
| `previous_evidence_checked` | v557 runtime sync report; prior ETH cap feasibility report; runtime read-only artifact snapshot under `/tmp/openclaw/cost_gate_learning_lane`. |
| `new_evidence_delta_required` | Distinct cap-envelope sensitivity result and fresh artifact-path/status evidence; not another P0 authorization audit. |
| `new_evidence_delta_found` | Runtime artifacts live under `/tmp/openclaw/cost_gate_learning_lane`; post-sync bounded auth latest now has correct `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED` status but still no authority; ETH executable exposure is stepwise at 0.01/0.02/0.03 ETH thresholds. |
| `anti_repeat_decision` | Do not repeat source fix, runtime sync, or P0 authorization read-only audit. Proceed only with source-only ETH cap-envelope sensitivity and TODO hygiene. |
| `action_taken_or_noop_reason` | Calculated ETH cap staircase from existing construction preview price/step metadata; recorded that any future ETH path needs a separate cap-envelope review and cannot displace AVAX under current cap. |
| `aggressive_profit_hypotheses` | See table below. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION` remains blocked until real candidate-scoped auth delta; if continuing source-only after the operator-requested pause, use `P1-AGGRESSIVE-ALPHA-CAP-ENVELOPE-EVIDENCE-FLOOR-SOURCE-ONLY`. |
| `why_not_repeating_current_blocker` | The ETH cap answer is now precise: current `10 USDT` cap cannot construct ETH Buy, and the first executable tier is `15.7105 USDT`. Repeating without fresh price/metadata/evidence would only restate the same block. |

## Evidence

Runtime read-only snapshot at `2026-06-26T07:03:49Z`:

| Artifact | Status | SHA256 | Note |
|---|---|---|---|
| `/tmp/openclaw/cost_gate_learning_lane/false_negative_candidate_friction_scorecard_latest.json` | `FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY` | `266e11c2...` | Top side-cell `grid_trading|ETHUSDT|Buy`; 10 ranked candidates. |
| `/tmp/openclaw/cost_gate_learning_lane/false_negative_candidate_packet_latest.json` | `COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW` | `c93b792c...` | Top false-negative `grid_trading|ETHUSDT|Buy`, net cushion `258.3905bps`. |
| `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_candidate_construction_preview_eth_buy_latest.json` | `CANDIDATE_CONSTRUCTION_NOT_FEASIBLE_UNDER_CAP` | `f4e36f14...` | Current `10 USDT` cap cannot construct positive rounded qty. |
| `/tmp/openclaw/cost_gate_learning_lane/cap_feasible_candidate_selection_avax_sell_20260625T214943Z.json` | `CAP_FEASIBLE_CANDIDATE_SELECTED_FOR_PREFLIGHT_REVIEW` | `909651b8...` | AVAX remains current-cap feasible selected candidate. |
| `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json` | `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED` | `c46dcd88...` | AVAX-scoped, decision `defer`, `typed_confirm_matches=false`, no authority id/object. |

ETH construction basis from the existing no-order preview:

| Field | Value |
|---|---|
| Candidate | `grid_trading|ETHUSDT|Buy`, 60m |
| Modeled scorecard signal | `258.3905bps` avg net, `7/7` positive, friction rank `1` |
| Current cap | `10.0 USDT` |
| Limit price / best bid | `1571.05` |
| Qty step | `0.01 ETH` |
| Min executable positive notional | `15.7105 USDT` |
| Current rounded qty/notional | `0.0 ETH` / `0.0 USDT` |
| Blockers | `rounded_qty_not_positive_under_cap`, `rounded_notional_below_min_notional`, `min_positive_qty_notional_exceeds_cap` |

## Cap Staircase

At recorded limit price `1571.05` and qty step `0.01`:

| Cap USDT | Rounded qty | Notional | Utilization | Decision |
|---:|---:|---:|---:|---|
| `10.0000` | `0.00` | `0.0000` | `0.00%` | Not constructible. |
| `15.0000` | `0.00` | `0.0000` | `0.00%` | Not constructible. |
| `15.7105` | `0.01` | `15.7105` | `100.00%` | First executable tier. |
| `16.0000` | `0.01` | `15.7105` | `98.19%` | Same exposure as first tier. |
| `20.0000` | `0.01` | `15.7105` | `78.55%` | Same exposure as first tier. |
| `25.0000` | `0.01` | `15.7105` | `62.84%` | Same exposure as first tier. |
| `31.4210` | `0.02` | `31.4210` | `100.00%` | Second executable tier. |
| `32.0000` | `0.02` | `31.4210` | `98.19%` | Same exposure as second tier. |
| `47.1315` | `0.03` | `47.1315` | `100.00%` | Third executable tier. |
| `50.0000` | `0.03` | `47.1315` | `94.26%` | Same exposure as third tier. |

Conclusion: ETH cap expansion is not continuous. The first possible ETH bounded Demo tier is exactly one step, `0.01 ETH` / `15.7105 USDT` at the recorded price, which is `57.105%` above the current `10 USDT` cap. That is a real exposure change and cannot be treated as a small order-placement tweak.

## Decision

Do not raise the cap and do not open an ETH order/probe path now.

ETH remains a high-upside research lead only. Reasons:

- Current cap cannot construct ETH Buy.
- The evidence is modeled and small sample: `7` outcomes and no candidate-matched fills.
- No candidate-matched fees/slippage/control path exists.
- The post-sync authorization latest artifact is clearer, but still `defer` / no typed confirm / no authority object.
- Any future ETH tier would require a separate operator/QC cap-envelope decision plus PM -> E3 -> BB before any order path.

AVAX remains the selected current-cap bounded Demo candidate, but `P0-BOUNDED-PROBE-AUTHORIZATION` is still blocked.

## Aggressive Profit Hypotheses

| Hypothesis | Scores | Why it might make money | Fastest safe test | Required data | Failure condition | Authority required | Max safe next action |
|---|---|---|---|---|---|---|---|
| ETH Tier-1 cap envelope | expected_net_pnl_upside High; evidence_strength Low-Medium; execution_realism Low now; cost_after_fees modeled favorable; time_to_test Medium; risk_to_account None now/Medium if cap changes; risk_to_governance Medium; autonomy_value Medium | ETH has the strongest modeled false-negative edge, and the first tier is a bounded discrete exposure rather than unlimited cap drift. | Source-only evidence-floor review: require larger sample, controls, fresh BBO/metadata, and cap-risk math before proposing any cap envelope. | Fresh scorecard, candidate-matched controls, fee/slippage labels, BBO, instrument metadata, portfolio exposure treatment. | Sample stays tiny, edge collapses after costs, or cap rise weakens survival/risk envelope. | Operator/QC cap-envelope approval plus PM -> E3 -> BB before any order. | Research packet only; no cap mutation. |
| AVAX scoped authorization admission | expected_net_pnl_upside High path-enabler; evidence_strength Medium-High; execution_realism blocked by auth; cost_after_fees favorable modeled; time_to_test Fast if valid auth appears; risk_to_account None now; risk_to_governance Medium; autonomy_value High | AVAX is current-cap feasible with `73.5511bps` modeled net and `48/48` positive modeled outcomes. | Review only a real AVAX-scoped typed-confirm/standing-auth artifact delta. | Exact false-negative preflight approval, bounded auth object, fresh BBO, cap construction, fees/fills/slippage lineage. | No exact auth, stale candidate, or any authority contamination. | Candidate-scoped auth plus E3/BB; no authority now. | Stop at authorization gate. |
| Current-cap low-price false-negative evidence floor | expected_net_pnl_upside Medium; evidence_strength Medium; execution_realism Medium; cost_after_fees Mixed; time_to_test Fast; risk_to_account None source-only; risk_to_governance Low; autonomy_value High | Lower-price cap-feasible symbols may preserve net edge inside the existing `10 USDT` cap without changing risk envelope. | Source-only evidence-floor filter for sample size, spread, markout controls, and proof-exclusion lineage. | Cap screen, scorecard rows, spread/markout controls, fee/slippage assumptions, lineage/proof exclusions. | Net cushion disappears after costs or no subgroup has reconstructable evidence. | Research only; E3/BB + bounded auth before any order. | Build proposal criteria, not orders. |

## Artifact Necessity

Artifacts created were limited to the required audit trail and handoff:

- session state `/tmp/openclaw/session_loop_state_20260626T070349Z_eth_cap_envelope_sensitivity_no_order.json`
- this PM report
- one Operator note
- TODO/changelog/memory/worklog updates

No runtime `_latest` overwrite, runtime job, PG query/write, Bybit call, order path artifact, or authority object was generated.
