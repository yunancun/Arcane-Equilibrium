# False-Negative Subset Mining: ETH Cap-Bound No-Order Packet

Date: 2026-06-26 06:54 CEST

## State

| Field | Value |
|---|---|
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-FALSE-NEGATIVE-SUBSET-MINING-NO-ORDER` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T045122Z_false_negative_subset_mining_no_order.json` |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P1-AGGRESSIVE-ALPHA-ETH-BUY-CAP-FEASIBILITY-PROPOSAL-NO-ORDER` |

This is a source-only review packet. It is not a candidate replacement for the current P0 bounded Demo path and grants no order/probe/live authority.

Role chain note: this round was handled PM-local because it did not change code/models, did not make a trading decision, and only summarized existing artifacts into a review-only packet. QC/MIT/AI-E are required for the next cap/risk proposal if it would recommend changing any bounded cap/risk envelope.

## Evidence Checked

Read-only runtime artifacts:

- `/tmp/openclaw/cost_gate_learning_lane/false_negative_candidate_friction_scorecard_latest.json`
  - generated `2026-06-26T04:30:54.770899Z`
  - status `FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY`
  - ranked candidates `10`
  - all authority/proof answers false/NONE; `source_only_research_artifact=true`
- `/tmp/openclaw/cost_gate_learning_lane/false_negative_candidate_packet_latest.json`
  - generated `2026-06-26T04:29:22.265261Z`
  - status `COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW`
  - ranked false-negative candidates `11`
- `/tmp/openclaw/cost_gate_learning_lane/false_negative_bounded_probe_preflight_latest.json`
  - candidate `grid_trading|ETHUSDT|Buy`
  - status `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION`
  - all order/probe/Cost Gate/live/proof answers false/NONE
- `/tmp/openclaw/cost_gate_learning_lane/candidate_universe_instrument_screen_false_negative_cap_feasible_20260625T214943Z.json`
  - cap `10 USDT`
  - `top_fit_by_rank=grid_trading|AVAXUSDT|Sell`
  - `fits_current_cap_count=8`
  - ETH current-cap exclusion recorded
- `/tmp/openclaw/cost_gate_learning_lane/cap_feasible_candidate_selection_avax_sell_20260625T214943Z.json`
  - selected `grid_trading|AVAXUSDT|Sell`
  - status `CAP_FEASIBLE_CANDIDATE_SELECTED_FOR_PREFLIGHT_REVIEW`
  - all order/probe/Cost Gate/live/proof answers false/NONE

## Subset Decision

Exactly one review-only alpha subset is selected for follow-up:

| Field | Value |
|---|---|
| subset | `grid_trading|ETHUSDT|Buy`, 60m |
| class | false-negative after current modeled cost |
| avg net | `258.3905bps` |
| net-positive | `7/7`, `100%` |
| friction rank | `1` |
| preflight | `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION` |
| current cap status | not constructible under `10 USDT` cap |
| min executable notional | about `15.7318 USDT` |
| blocking gates | `min_positive_qty_notional_exceeds_cap`, `rounded_notional_below_min_notional`, `rounded_qty_not_positive_under_cap` |

Interpretation:

- ETH Buy has the highest modeled upside in the latest false-negative scorecard.
- It is not the current bounded Demo candidate because it fails the existing `10 USDT` cap envelope.
- AVAX Sell remains the only current cap-feasible bounded Demo candidate under the existing cap and authorization posture.
- The fastest safe ETH next step is a source-only cap/risk feasibility proposal, not a bounded Demo probe.

## Review-Only Proposal Packet

`proposal_id`: `P1-ETH-BUY-CAP-FEASIBILITY-NO-ORDER-20260626`

Goal: determine whether ETH Buy's minimum executable notional can fit inside an operator/QC-defined bounded Demo risk envelope without lowering global Cost Gate or granting runtime/order/probe authority.

Fastest safe test:

1. Source-only QC/MIT cap feasibility review for `grid_trading|ETHUSDT|Buy`.
2. Compare current `10 USDT` cap against minimum executable notional around `15.73 USDT`.
3. If and only if a reviewed bounded cap envelope exists, produce a fresh no-order construction preview and E3/BB order-envelope review.
4. Actual order/probe remains blocked until bounded Demo authorization is valid and admitted.

Required data:

- latest false-negative scorecard and candidate packet
- current instrument metadata, qty step, tick size, min notional, BBO freshness
- bounded cap policy and operator/QC-defined risk envelope
- fee/slippage estimate and candidate-matched controls
- current authorization/admission status

Failure conditions:

- required cap exceeds operator/QC risk envelope
- ETH sample remains too small for bounded Demo priority (`7` outcomes only)
- fresh market metadata changes min executable notional unfavorably
- candidate-matched touchability/fill lineage cannot be made reconstructable
- any proposal tries to lower global Cost Gate or bypass authorization

Authority required:

- current packet: none; research/proposal only
- cap envelope change: operator/QC-defined bounded risk review
- runtime/order path: PM -> E3 -> BB -> PM plus valid bounded Demo authorization

## Constraints Checked

- No global Cost Gate lowering.
- No live/mainnet.
- No Bybit/API/order/cancel/modify call.
- No PG write; the artifacts were read only.
- No runtime source sync, service restart/rebuild, crontab/env mutation, `_latest` overwrite, Rust writer/adapter enablement, plan mutation, or authorization grant.
- No proof/promotion/profitability claim.
- Proof exclusions remain active: `flash_dip_buy`, cleanup/risk-close, unattributed fills, local stale rows, artifact counts, source-smoke, single-window MM positives, replay-only results.

## Aggressive Profit Hypotheses

| Hypothesis | Scores | Why it might make money | Fastest safe test | Required data | Failure condition | Authority |
|---|---|---|---|---|---|---|
| ETH Buy min-notional cap feasibility | upside High; evidence Medium-Low due `7` outcomes; realism Medium; cost Good; time Fast; account risk None source-only; governance Low now, Medium if cap changes | Latest scorecard shows `258.3905bps` modeled net and measured friction rank 1, but current cap blocks construction. | QC/MIT source-only cap/risk review; no-order construction preview only if cap envelope is approved. | Scorecard, cap policy, instrument metadata, BBO, min notional, fee/slippage, controls. | Required cap exceeds risk envelope, sample too small, or fresh construction remains infeasible. | Research now; operator/QC for cap envelope; E3/BB + bounded auth before any order. |
| AVAX remains current bounded candidate | upside High; evidence Medium; realism Medium; cost Good; time Fast after auth; account risk Low if capped; governance Medium; autonomy High | AVAX is cap-feasible under `10 USDT`, has `73.5511bps` modeled net and `48/48` positive outcomes. | Valid AVAX-scoped authorization plus fresh E3/BB review, then one capped near-touch-or-skip attempt. | Auth object, fresh BBO, fills, fees, slippage, candidate controls. | No valid auth, no touch, stale BBO, taker fill, missing lineage, or net <= 0. | Structured bounded Demo authorization + E3/BB required. |
| Cap-feasible low-price false-negative basket | upside Medium; evidence Medium; realism Medium; cost Mixed; time Medium; account risk None source-only; governance Low | ETC/SUI/FIL/APT/UNI/XRP/OP fit current cap, but lower net cushions may still reveal regime filters. | Source-only filter/regime split over cap-feasible rows; do not select more than one bounded candidate without P0 reselection. | Scorecard rows, cap screen, regimes, spread/markout, controls. | Edge disappears after regime split or cost/slippage exceeds cushion. | Research/proposal only. |

## Status

`DONE_WITH_CONCERNS`.

Concern: ETH Buy is high-upside but not executable inside the current `10 USDT` cap. Treat it as a source-only cap/risk proposal path. AVAX remains the current cap-feasible bounded Demo candidate, still blocked by authorization.
