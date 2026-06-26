# Profit Candidate Selection - AVAX Review Packet

Timestamp: 2026-06-26T03:23Z

## Blocker

`P0-PROFIT-CANDIDATE-SELECTION`

## Decision

`DONE_WITH_CONCERNS`.

Selected exactly one bounded Demo candidate for review-only follow-up:

- side-cell: `grid_trading|AVAXUSDT|Sell`
- source class: Cost Gate false-negative after current cost
- horizon: `60m`
- candidate status: review-only, no authority

This packet does not grant bounded-probe, order, live, runtime, adapter, Rust
writer, PG-write, Cost Gate, or promotion authority.

## Why This Candidate

The false-negative packet has a higher raw candidate, `grid_trading|ETHUSDT|Buy`,
but the cap-feasible screen excludes ETH under the current `10 USDT` bounded
Demo cap. The next cap-feasible false-negative candidate is
`grid_trading|AVAXUSDT|Sell`.

Evidence from the cap-feasible selection packet:

- avg gross: `77.5511bps`
- modeled average cost: `4.0bps`
- avg net / net cost cushion: `73.5511bps`
- net-positive outcomes: `48/48` (`100.0%`)
- min net: `25.1271bps`
- max net: `112.0387bps`
- minimum required Demo notional: `5.0 USDT`
- current cap: `10.0 USDT`
- instrument status: `Trading`
- global Cost Gate lowering recommended: `false`
- probe/order authority granted: `false/false`

## Evidence Checked

Primary artifacts:

- `/tmp/openclaw/session_loop_state_20260626T032000Z_profit_candidate_selection.json`
- `/tmp/openclaw/local_chain_smoke_20260625T232303Z/inputs/false_negative_candidate_packet_latest.json`
- `/tmp/openclaw/local_chain_smoke_20260625T232303Z/inputs/cap_feasible_candidate_selection_avax_sell_20260625T214943Z.json`
- `/tmp/openclaw/local_chain_smoke_20260625T232303Z/inputs/false_negative_operator_review_avax_sell_cap_feasible_20260625T214943Z.json`
- `/tmp/openclaw/local_chain_smoke_20260625T232303Z/outputs/false_negative_bounded_probe_preflight_avax_sell_20260625T232303Z.json`
- `/tmp/openclaw/local_chain_smoke_20260625T232303Z/outputs/bounded_probe_touchability_preflight_avax_sell_20260625T232303Z.json`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-23--mm_current_fee_confirmation_packet.md`

Artifact hashes checked:

- false-negative packet: `a961570142339466228e465cb964a663547e7086f83f91acb9df9878c8fe75ad`
- cap-feasible selection: `909651b8428c0903b7d0e415b17e65cec6f95d2f73fde6e7290a87fd49c9d01e`
- AVAX operator review: `3e7cbb774cb351eb184f5aea07d8f723abcf69132d423ba0a74397c792037b9b`
- bounded preflight: `d532255c773f25931f113bde67171f94e1c87963aa73c4e809339ed1b59fe916`
- touchability preflight: `1b1210140effdceae3d4d928487cc085c3c96ec4be11ea315cf627a11c47ef66`

The `2026-06-26` cleanup report is used only as exchange-book hygiene evidence:
post-action open orders `0`, nonzero positions `0`. Cleanup/risk-close/
unattributed/local-stale rows remain proof-excluded.

## Review Chain

QC: `PASS_WITH_CONCERNS`.

- AVAX is acceptable as exactly-one review-only candidate.
- ETH is higher raw rank but excluded under the current cap.
- MM SOXLUSDT is weaker for immediate selection: `0.715bps` net, one positive
  window, no repeat/OOS/maker-realism confirmation.
- Existing fills are non-candidate and cannot prove touchability or profit.

MIT: valid but bounded lineage.

- AVAX lineage is valid for candidate selection/preflight only.
- It is invalid as bounded-probe authorization, construction readiness,
  touchability proof, PnL proof, or promotion evidence.
- The older `bounded_probe_lower_price_reroute_review_latest.json` must not be
  overclaimed because the newer chain smoke is
  `LOWER_PRICE_REROUTE_ALIGNMENT_BLOCKED`.

BB: approve review-only packet; block active probe/order.

- Cap/min-notional are feasible for review: `10 USDT` cap and `5 USDT` minimum
  notional.
- Fee/slippage realism must be proven with realized fee rate, maker/taker
  label, BBO freshness, fill/slippage rows, and markout review.
- Candidate-matched touchability is missing.

## Proof Exclusions

The following must not count toward Cost Gate proof, bounded-probe proof,
promotion, or risk-adjusted net PnL:

- `flash_dip_buy`
- cleanup/risk-close fills
- `unattributed:bybit_auto`
- local stale `Working` rows from health [68]
- non-candidate AVAX fills/touchability rows
- artifact counts alone
- source smoke alone
- single-window MM positive result
- replay-only results

## Current Blocker

The hard blocker before active bounded probe/order is:

- `CANDIDATE_TOUCHABILITY_DATA_REQUIRED`
- candidate-reviewed orders: `0`
- candidate fill rows: `0`
- existing fill flow: non-candidate only

Therefore the max safe next action is source/read-only:

`P0-BOUNDED-PROBE-FIRST-ATTEMPT-TOUCHABILITY-BOOTSTRAP-SOURCE-ONLY`

This should produce a no-authority near-touch-or-skip design contract for the
exact side-cell `grid_trading|AVAXUSDT|Sell`, requiring fresh BBO/cap checks,
candidate-matched order/fill/fee/slippage lineage, and separate E3/BB/operator
authorization before any Demo order attempt.

## Aggressive Profit Hypotheses

| Hypothesis | Why it might make money | Fastest safe test | Required data | Failure condition | Authority | Scores |
|---|---|---|---|---|---|---|
| AVAX false-negative first-attempt touchability bootstrap | Modeled current-cost net cushion is large (`73.5511bps`) and the candidate fits the current bounded Demo cap. | Source-only near-touch-or-skip contract for first candidate-matched attempt. | Candidate packet, fresh BBO/cap metadata, Decision Lease lineage, fee/slippage capture contract. | Contract cannot stay no-authority, or it cannot produce candidate-matched reconstructable evidence. | Source/review only. | upside high; evidence medium; realism medium; cost medium; time short; account risk low; governance risk medium-low; autonomy high |
| AVAX regime filter before probe | False-negative edge may concentrate in specific volatility/spread regimes, improving Demo sample quality. | Source-only filter proposal using existing blocked-outcome rows, with no Cost Gate lowering. | 60m markouts, spread/BBO age, volatility/funding/session features. | Edge disappears after OOS or filter leaves too few samples. | Research/proposal only. | upside medium-high; evidence medium; realism medium; cost unchanged; time short; account risk low; governance risk low; autonomy high |
| MM current-fee repeat-window branch | Maker route could reduce fees and spread cost if repeat/OOS confirms it. | Accumulate independent windows for the same current-fee-positive SOXL cell. | MM confirmation history, maker fills, adverse-selection controls, current fee tier. | Remains single-window or net edge vanishes after fees. | Research/proposal only. | upside medium; evidence low; realism medium; cost sensitive; time medium; account risk low; governance risk low; autonomy medium |

## State Transition

- `active_blocker_id`: `P0-PROFIT-CANDIDATE-SELECTION`
- `anti_repeat_decision`: `PROCEED_NEW_EVIDENCE_DELTA`
- `status`: `DONE_WITH_CONCERNS`
- `next_blocker_id`: `P0-BOUNDED-PROBE-AUTHORIZATION`
- `why_not_repeating_current_blocker`: exactly one review-only candidate is now
  selected; repeating selection without new candidate, cap, fee, touchability,
  or artifact delta would add no evidence.

## Boundaries Preserved

No Bybit call, order, cancel, modify, PG write, runtime source sync, service
restart, crontab/env mutation, adapter/Rust writer enablement, global Cost Gate
change, probe/order/live authority, or promotion proof occurred in this
checkpoint.
