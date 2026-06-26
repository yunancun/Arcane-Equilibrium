# Cap-Feasible Low-Price Filter No-Order Packet

Date: 2026-06-26 07:14 CEST

## Required Round Output

| Field | Value |
|---|---|
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-CAP-FEASIBLE-LOW-PRICE-REGIME-FILTER-NO-ORDER` |
| `blocker_goal` | Source-only split of current-cap-feasible false-negative rows by verifiable filter fields; produce exactly one review-only proposal or rejection. |
| `profit_relevance` | Searches for a fee-aware, current-cap-feasible path after ETH Buy was rejected/deferred for cap infeasibility. |
| `constraints_checked` | No Cost Gate lowering, no live promotion, no Bybit order/cancel/modify, no PG write, no runtime/env/crontab/service mutation, no adapter/writer enablement, no order/probe authority, no profit/proof claim. |
| `previous_evidence_checked` | `2026-06-26--eth_buy_cap_feasibility_no_order.md`; `2026-06-26--false_negative_subset_mining_eth_cap_bound_no_order.md`; runtime scorecard/candidate-packet/cap-screen/auth artifacts. |
| `new_evidence_delta_required` | A distinct source-only current-cap-feasible filter decision, not repeated ETH cap feasibility, P0 candidate selection, or authorization audit. |
| `new_evidence_delta_found` | AVAX is the only champion under a clean-BBO/high-cushion/current-cap-feasible filter; SUI/FIL pass only as source-only controls; no regime label exists in current artifacts. |
| `anti_repeat_decision` | Proceeded as distinct source-only blocker. Do not repeat without fresh scorecard/cap-screen/authorization or a real regime-label/outcome evidence delta. |
| `action_taken_or_noop_reason` | Produced one review-only filter proposal; no new P0 candidate, no order/probe authority, no runtime mutation. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P1-AGGRESSIVE-ALPHA-AVAX-SUI-FIL-MATCHED-CONTROL-DESIGN-NO-ORDER` |
| `why_not_repeating_current_blocker` | Current-cap-feasible row set is now filtered and classified; rerunning the same rows would not add evidence. |

PM handled this locally because the work was read-only synthesis from existing artifacts and did not change code, risk, candidate selection authority, or runtime state. QC/MIT should be used if a later step proposes changing the P0 bounded candidate, cap/risk envelope, or model/data contract.

## Evidence

Runtime read-only checks only. No artifact was generated or overwritten.

| Artifact | Status | SHA256 |
|---|---|---|
| `candidate_universe_instrument_screen_false_negative_cap_feasible_20260625T214943Z.json` | `8` current-cap-feasible rows | `09627dcd46526e7c15d1084883aa034fa6bc2e0323667206f2ef59bdefa83ecb` |
| `false_negative_candidate_friction_scorecard_latest.json` | `FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY` | `0d01ca3d9a93ca2178e1fbb486116394bfe89eb9423a9862ddfa6fc830eaa0f7` |
| `false_negative_candidate_packet_latest.json` | `COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW` | `382274a70f72050cab61431186fe4bdb366eac76f9e053e63d2d5e6c5f55a8a9` |
| `bounded_probe_operator_authorization_latest.json` | `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, generated `2026-06-26T05:15:05Z`; still defer/review-only | `c28549734d081d3ffa0c8ed5961f82937071ab40dcb40348a1f6e8cb31ef116c` |

Filter used for this source-only proposal:

- `fits_current_cap=true`
- `best_bid > 0` and `best_ask > 0`
- `spread_bps <= 2.0`
- `net_cost_cushion_bps >= 15.0`
- `net_positive_pct >= 75.0`
- `outcome_count >= 16`
- no Cost Gate lowering, no authority/proof flags

This is a proposal filter, not a promotion gate. It deliberately uses only fields present in the current artifacts.

## Row Classification

| Row | Classification | Evidence | Reason |
|---|---|---|---|
| `grid_trading|AVAXUSDT|Sell` | Champion; keep current P0 candidate | `73.5511bps`, `100%`, `48` outcomes, spread `1.6108bps`, min required `5.0 USDT` | Strongest current-cap-feasible row with complete BBO and clean cushion. |
| `grid_trading|SUIUSDT|Sell` | Source-only control | `17.424bps`, `88%`, `25` outcomes, spread `1.4725bps`, min required `6.792 USDT` | Passes filter but materially weaker than AVAX and not a new P0 candidate. |
| `grid_trading|FILUSDT|Buy` | Source-only control | `17.8368bps`, `75%`, `16` outcomes, spread `1.3663bps`, min required `5.0 USDT` | Passes lower bound only; useful as control, not candidate replacement. |
| `grid_trading|ETCUSDT|Sell` | Reject for this round | ask `0.0` | Incomplete BBO; cannot support execution-realism proposal. |
| `grid_trading|APTUSDT|Buy` | Reject for this round | ask `0.0`, `13.6046bps`, `70.4545%` | Incomplete BBO plus thinner cushion/hit rate. |
| `grid_trading|UNIUSDT|Sell` | Reject for this round | `6.805bps`, `69.2308%`, spread `3.4746bps` | Cushion and hit rate too thin; spread too wide. |
| `grid_trading|XRPUSDT|Sell` | Reject for this round | `4.1502bps` | Cushion too thin after fees/slippage. |
| `grid_trading|OPUSDT|Buy` | Reject for this round | `4.1525bps`, `63.6364%`, `11` outcomes | Cushion, hit rate, and sample too weak. |

## Decision

Exactly one review-only proposal is accepted:

`proposal_id`: `P1-CAP-FEASIBLE-CLEAN-BBO-HIGH-CUSHION-FILTER-20260626`

Proposal:

- Keep `grid_trading|AVAXUSDT|Sell` as the current cap-feasible champion.
- Treat `grid_trading|SUIUSDT|Sell` and `grid_trading|FILUSDT|Buy` as source-only matched controls for future analysis.
- Do not select SUI/FIL as bounded Demo candidates without reopening `P0-PROFIT-CANDIDATE-SELECTION`.
- Do not claim regime proof. Current artifacts do not contain leak-free regime labels or markout buckets.
- Do not advance any order/probe path without valid AVAX-scoped authorization and PM -> E3 -> BB review.

Concern: the blocker name includes regime/filter, but current artifacts only support the filter part. A true regime split requires a later data-design step joining false-negative outcomes to point-in-time regime labels.

## Aggressive Profit Hypotheses

| Hypothesis | Scores | Why it might make money | Fastest safe test | Required data | Failure condition | Authority |
|---|---|---|---|---|---|---|
| Clean-BBO high-cushion current-cap-feasible filter | upside Medium-High; evidence Medium; realism Medium; cost Good for AVAX; time Fast source-only; account risk None; governance Low; autonomy High | Excludes broken-BBO and thin-cushion rows while staying inside the `10 USDT` cap. | Rerun on the next scorecard/cap-screen refresh; if AVAX remains champion and valid auth appears, go through E3/BB order-envelope review. | Fresh scorecard, cap screen, complete BBO, fees/slippage, candidate-matched controls, auth state. | AVAX loses clean-BBO/high-cushion status or lineage cannot be constructed. | Research now; structured bounded Demo auth + E3/BB before order. |
| SUI/FIL as no-order controls | upside Medium; evidence Low-Medium; realism Medium; cost Moderate; time Fast source-only; account risk None; governance Low; autonomy Medium | Controls can test whether AVAX is symbol-specific or part of a broader low-price grid edge. | Source-only matched-control design against AVAX. | Same horizon rows, fee/slippage model, eventual candidate-matched lineage. | Controls fail fresh filter or cannot align to proof contract. | Research only; no order authority. |
| Future regime split with point-in-time labels | upside Medium; evidence Low now; realism Unknown; cost Unknown; time Medium; account risk None; governance Low; autonomy High | A true regime split may avoid false positives if edge is volatility/trend-state specific. | Source-only requirements packet for joining outcomes to leak-free regime labels. | Regime labels, blocked-signal timestamps, outcome rows, fees/slippage. | No leak-free labels or no subgroup survives costs. | Research/data design only; PG read needs separate reviewed runtime data step if used. |

## Artifact Necessity

Created only the mandatory handoff records:

- updated session state: `/tmp/openclaw/session_loop_state_20260626T051422Z_cap_feasible_low_price_filter_no_order.json`
- this PM report
- one short operator note
- TODO/changelog/worklog/memory updates

No new research JSON artifact, `_latest` overwrite, runtime job, PG write, Bybit call, or order-path artifact was created.
