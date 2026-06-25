# PM Report: AVAX Candidate-Scoped Chain Smoke

Date: 2026-06-25
Status: DONE_WITH_CONCERNS
Active blocker: `P0-BOUNDED-PROBE-AVAX-CANDIDATE-SCOPED-CHAIN-SMOKE-DEMO-ONLY`
Next blocker: `P0-BOUNDED-PROBE-AVAX-CANDIDATE-TOUCHABILITY-BOOTSTRAP-SOURCE-ONLY`

## Decision

Ran a timestamped local no-authority AVAX chain smoke from copied/read-only runtime inputs. The chain confirms that the v523 source patch works for candidate scoping: `grid_trading|AVAXUSDT|Sell` now reaches a reviewable autonomous proposal and false-negative bounded Demo preflight.

The chain still fails closed before construction/admission because current Demo touchability evidence has no candidate-matched `grid_trading|AVAXUSDT|Sell` orders. Existing AVAX rows are flash/risk-close evidence and must not count as bounded-probe proof.

## Inputs

- Source head: `5aa93f05e6ceec5c822551fbee98c1b64175e20d`.
- Linux runtime head snapshot: `e0c2a0e17c8d00883c935d1ceb6897ccd9b9e36c`, clean at 2026-06-25T23:23Z.
- Local staging path: `/tmp/openclaw/local_chain_smoke_20260625T232303Z`.
- Copied/read-only inputs:
  - `learning_ssot_decision_latest.json`
  - `false_negative_candidate_packet_latest.json`
  - `false_negative_operator_review_avax_sell_cap_feasible_20260625T214943Z.json`
  - `cap_feasible_candidate_selection_avax_sell_20260625T214943Z.json`
  - `demo_order_to_fill_gap_latest.json`

## Output Statuses

| Output | Status | SHA256 |
|---|---|---|
| `autonomous_parameter_proposal_avax_sell_20260625T232303Z.json` | `REVIEWABLE_PARAMETER_PROPOSAL_READY` | `e5917d9b7828d18c9888929ad7aa2dff8ec6b37c251afcf69f12e5564f9f5e03` |
| `false_negative_bounded_probe_preflight_avax_sell_20260625T232303Z.json` | `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION` | `d532255c773f25931f113bde67171f94e1c87963aa73c4e809339ed1b59fe916` |
| `bounded_probe_touchability_preflight_avax_sell_20260625T232303Z.json` | `CANDIDATE_TOUCHABILITY_DATA_REQUIRED` | `1b1210140effdceae3d4d928487cc085c3c96ec4be11ea315cf627a11c47ef66` |
| `bounded_probe_placement_repair_plan_avax_sell_20260625T232303Z.json` | `CANDIDATE_TOUCHABILITY_DATA_REQUIRED` | `bf8fa0fe36be32b0c8d977a8fc0fe7743feec124215179a68ad4d6e9ee71c8d1` |
| `bounded_probe_authority_patch_readiness_avax_sell_20260625T232303Z.json` | `PLACEMENT_REPAIR_PLAN_NOT_READY` | `ceaf8c84a7aaae336dd29404bf5c7146c9bc59ec06e7225941ce06fbe20f5f83` |
| `bounded_probe_operator_authorization_avax_sell_20260625T232303Z.json` | `PLACEMENT_REPAIR_PLAN_NOT_READY` | `e76a8e06bcecd46d4cfa8bbd6cf498e68998369adae17d9be168d2a338aeee34` |
| `bounded_probe_lower_price_reroute_review_avax_sell_20260625T232303Z.json` | `LOWER_PRICE_REROUTE_ALIGNMENT_BLOCKED` | `97021201e2b3d08ca24d1238415e9f06e87cfebe629d0b16681af06d35f93a0e` |

## Blocker

The first hard blocker is `CANDIDATE_TOUCHABILITY_DATA_REQUIRED` with reason `fill_flow_exists_only_for_non_candidate_orders`. Downstream packets correctly remain not ready:

- placement repair cannot become ready from unrelated AVAX flash/risk-close rows;
- authority patch readiness remains `PLACEMENT_REPAIR_PLAN_NOT_READY`;
- operator authorization emits no authorization object;
- lower-price reroute review remains alignment-blocked because required downstream artifacts are not ready.

## Boundary

No Bybit call, no private/auth endpoint, no order/cancel/modify, no PG write, no `_latest` overwrite, no service/env/crontab/runtime mutation, no Cost Gate lowering, no cap/freshness widening, no Rust writer/adapter enablement, no probe/order/live authority, and no promotion proof.

## Aggressive Profit Hypotheses

| Hypothesis | Why it might make money | Fastest safe test | Required data | Failure condition | Authority | Score |
|---|---|---|---|---|---|---|
| AVAX first-attempt touchability bootstrap | AVAX preflight is READY and has 73.5511bps avg net with 48/48 net-positive blocked outcomes; the missing piece is candidate-matched execution realism. | Source-only no-authority first-attempt near-touch-or-skip design contract for zero candidate orders. | Current preflight, order-to-fill gap, cap/price limits, candidate identity, BBO freshness rules. | Contract would imply proof/authority without a real candidate attempt, or cannot remain cap/risk/freshness gated. | Source/test/docs only. | upside high; evidence medium; realism medium; cost medium; time short; account risk low; governance risk medium-low; autonomy high |
| Candidate-specific touchability collection | A single capped candidate-matched Demo attempt could reveal whether the false-negative edge is touchable without broad overhang. | After separate review/authority, one bounded Demo candidate attempt with immediate order-to-fill and fee/slippage lineage. | Fresh operator authorization object, Rust admission readiness, BBO, fills/order states. | No fill/touch under near-touch rules, or realized net after fees/slippage underperforms matched controls. | Requires separate runtime/exchange authority; not granted here. | upside high; evidence medium; realism high if authorized; cost medium; time medium; account risk bounded; governance risk high unless gated; autonomy high |
| MM maker repeat-window branch | If AVAX blocks on touchability, a maker/MM cell may still provide a lower-governance learning path with fee-aware execution. | Source-only repeat-window/OOS maker-realism scorecard. | Independent windows, maker fee assumptions, fill quality, adverse-selection controls. | Edge remains single-window or disappears after current fees. | Research/source-only. | upside medium; evidence low-medium; realism medium; cost sensitive; time medium; account risk low; governance risk low; autonomy medium |

## Next Safe Action

Advance `P0-BOUNDED-PROBE-AVAX-CANDIDATE-TOUCHABILITY-BOOTSTRAP-SOURCE-ONLY`: decide whether zero candidate-matched order history may produce a review-only first-attempt near-touch-or-skip design contract. If code changes are needed, use the normal source chain `PM -> PA/E1 -> E2 -> E4 -> QA/PM`.
