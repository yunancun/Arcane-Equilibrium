# AVAX / SUI / FIL Matched-Control Design No-Order Packet

Date: 2026-06-26 07:22 CEST

## Required Round Output

| Field | Value |
|---|---|
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-AVAX-SUI-FIL-MATCHED-CONTROL-DESIGN-NO-ORDER` |
| `blocker_goal` | Define a source-only matched-control evidence contract for AVAX champion versus SUI/FIL controls. |
| `profit_relevance` | Prevents false profit claims by specifying how future AVAX bounded outcomes must be compared against controls after real fees/slippage. |
| `constraints_checked` | No Cost Gate lowering, no live promotion, no Bybit order/cancel/modify, no PG write, no runtime/env/crontab/service mutation, no adapter/writer enablement, no order/probe authority, no profit/proof claim. |
| `previous_evidence_checked` | `2026-06-26--cap_feasible_low_price_filter_no_order.md`; existing result-review, execution-realism, and proof-exclusion source contracts. |
| `new_evidence_delta_required` | A non-repeated source-only control design, not a new candidate selection or authorization audit. |
| `new_evidence_delta_found` | Existing result review supports same-side-cell blocked controls for the active candidate; it does not support SUI/FIL cross-symbol controls as proof. |
| `anti_repeat_decision` | Proceeded as distinct source-only blocker. Do not repeat without source contract or outcome evidence changes. |
| `action_taken_or_noop_reason` | Produced no-order matched-control design; SUI/FIL are research controls only; AVAX proof must use same-side-cell controls and candidate-matched fill lineage. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION` |
| `why_not_repeating_current_blocker` | The control semantics are now explicit; repeating would not add evidence without new source/outcome data. |

PM handled this locally because this was source-contract synthesis and docs/TODO only. No code change was made. If future work implements cross-symbol control semantics, it must use the source/test chain `PM -> PA/E1 -> E2 -> E4 -> QA/PM`.

TODO maintenance was also applied in this checkpoint: `TODO.md` keeps maintenance-standard operational queue statuses (`DONE/BLOCKED/WAITING/DEFERRED`) and preserves state-machine outcomes such as `DONE_WITH_CONCERNS` or `BLOCKED_BY_RUNTIME_AUTHORIZATION` in a separate `Loop decision` column.

## Existing Contracts Checked

| Contract | Relevant behavior |
|---|---|
| `helper_scripts/research/cost_gate_learning_lane/proof_exclusion.py` | Unattributed or lineage-incomplete fill-backed rows are proof-excluded. Missing candidate lineage, order linkage, exchange order mapping, fill execution mapping, intent lineage, risk verdict, fee, slippage, close state, or source artifact linkage excludes the row from proof. |
| `helper_scripts/research/cost_gate_learning_lane/bounded_probe_result_review.py` | Reviews future bounded Demo outcomes against the sealed preflight design; consumes probe admissions/outcomes and matched blocked-signal controls for the same side-cell; preserves no-authority/no-Cost-Gate-lowering boundary. |
| `helper_scripts/research/cost_gate_learning_lane/bounded_probe_execution_realism_review.py` | Diagnoses positive probe under-capture versus controls using fill-backed %, gross/cost/slippage gap, and entry-delay gap; excludes rows with proof-exclusion reasons. |

## Design

Two control layers are required:

1. **Proof controls for AVAX**

   These are mandatory for any future `P0-PROFIT-OUTCOME-REVIEW`.

   Required properties:

   - candidate: `grid_trading|AVAXUSDT|Sell`, 60m
   - valid bounded Demo authorization and PM -> E3 -> BB order-envelope review happened before any order
   - candidate-matched probe admission and outcome rows
   - same-side-cell blocked-signal controls for `grid_trading|AVAXUSDT|Sell`
   - realized `net_bps` after fees/slippage
   - maker/taker label and actual fee/cost bps
   - BBO/entry context sufficient for execution realism
   - orderLinkId/exchange order/fill/intent/risk/source artifact lineage
   - no proof-exclusion reasons
   - no `flash_dip_buy`, cleanup/risk-close, unattributed, local stale, artifact-count, source-smoke, single-window MM, or replay-only proof contamination

2. **Research controls for SUI/FIL**

   These are useful for autonomy and candidate robustness, but they are not AVAX proof.

   Allowed use:

   - compare fresh scorecard/cap-filter rows over the same 60m horizon
   - check whether SUI/FIL still pass clean-BBO/high-cushion/current-cap filters
   - detect whether AVAX champion status is a one-off artifact
   - inform a future P0 candidate-selection reopen if new evidence justifies it

   Prohibited use:

   - SUI/FIL rows must not count as AVAX bounded-probe proof
   - SUI/FIL rows must not promote AVAX or lower Cost Gate
   - SUI/FIL must not become bounded candidates without reopening `P0-PROFIT-CANDIDATE-SELECTION`
   - cross-symbol controls must not bypass same-side-cell proof or proof-exclusion rules

## Pass / Fail Criteria For Future Outcome Review

Future AVAX outcome review may advance only if all are true:

- valid AVAX-scoped authorization existed before the attempt
- all candidate-matched AVAX probe rows have no proof-exclusion reasons
- average realized net PnL after fees/slippage is positive and clears the sealed preflight threshold
- net-positive rate clears the sealed preflight threshold
- same-side-cell blocked controls do not outperform the probe after costs
- execution realism review does not show unexplained fill-backed, fee/slippage, gross capture, or delay gaps
- SUI/FIL research controls do not contradict AVAX champion status on fresh evidence

Immediate failure conditions:

- any proof-excluded AVAX fill is used as proof
- any unattributed or cleanup/risk-close fill is counted
- SUI/FIL cross-symbol rows are counted as AVAX proof
- global Cost Gate lowering is proposed from this evidence
- order/probe/live authority is inferred from this design packet

## Aggressive Profit Hypotheses

| Hypothesis | Scores | Why it might make money | Fastest safe test | Required data | Failure condition | Authority |
|---|---|---|---|---|---|---|
| AVAX same-side-cell proof controls before Cost Gate learning | upside High if auth/outcomes arrive; evidence Medium design-only; realism Medium pending outcomes; cost must be measured; time Fast after auth; account risk None now; governance Low; autonomy High | Forces future AVAX outcomes to beat same side-cell controls after real fees/slippage. | After valid AVAX auth/probe, run existing result and execution-realism reviews with proof exclusions. | AVAX admissions/outcomes, same side-cell controls, fill lineage, fees, slippage, BBO, proof keys. | No candidate-matched fills, proof exclusions, net <= controls, or execution realism gap. | Research now; bounded auth + E3/BB before order. |
| SUI/FIL cross-symbol research controls | upside Medium; evidence Low-Medium; realism research-only; cost modeled only; time Fast source-only; account risk None; governance Low if not proof; autonomy Medium | Tests whether AVAX edge is a one-off artifact or broader low-price grid behavior. | Fresh source-only filter comparison over same horizon. | Fresh cap screen/scorecard, fee/slippage assumptions, optional regime labels. | SUI/FIL outperform AVAX or fail fresh filters. | Research only; no proof authority. |
| Future cross-symbol control code contract | upside Medium; evidence Low now; realism N/A; time Medium; account risk None; governance Medium if misdesigned; autonomy High | Could add formal cross-symbol controls without contaminating proof semantics. | PA/E1/E2/E4 source/test design only if fresh evidence justifies it. | Existing result-review semantics, control identity rules, leakage controls, proof exclusions. | Blurs candidate proof semantics or promotes controls without P0 reselection. | Source/test/docs only. |

## Stop Condition

All currently selected source-only blockers in the v548 queue are closed. The next blocker is `P0-BOUNDED-PROBE-AUTHORIZATION`, which remains `BLOCKED_BY_RUNTIME_AUTHORIZATION` until a valid AVAX-scoped authorization object or exact typed confirm appears and then passes E3/BB review.

No runtime/exchange action was taken.
