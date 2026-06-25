# PM Report: AVAX Fresh Reroute Chain Refresh Blocked, TODO Hygiene

Date: 2026-06-25
Status: DONE_WITH_CONCERNS
Active blocker: `P0-BOUNDED-PROBE-AVAX-FRESH-REROUTE-CHAIN-REFRESH-DEMO-ONLY`
Next blocker: `P0-BOUNDED-PROBE-AVAX-CANDIDATE-SPECIFIC-REROUTE-CHAIN-SOURCE-ONLY`

## Decision

Stopped before generating another runtime artifact or running another public quote. The AVAX lower-price reroute chain cannot be refreshed safely from current evidence without either using stale AVAX artifacts, mixing ETH latest artifacts into an AVAX chain, or creating a fake freshness story.

The useful next action is source-only: make the reroute review path candidate-scoped and timestamped so AVAX can be refreshed without relying on `_latest` artifacts that have drifted to ETH.

## Evidence Checked

- Source head: `ce4d7b501b8e0a3fb10cc7d333ca0b312d2cfb02`.
- Linux runtime checkout snapshot: `e0c2a0e17c8d00883c935d1ceb6897ccd9b9e36c`, clean at 2026-06-25T22:53Z.
- AVAX quote READY artifact: `/tmp/openclaw/cost_gate_learning_lane/bbo_freshness_public_quote_capture_avax_sell_20260625T223840Z.json`, sha `fe36f2dd0c4bbe683cd85b45e4a4feb76cc7a8542646d6700818a1b8a89ee605`.
- Fresh AVAX selection: `cap_feasible_candidate_selection_avax_sell_20260625T214943Z.json`, sha `909651b8428c0903b7d0e415b17e65cec6f95d2f73fde6e7290a87fd49c9d01e`, status `CAP_FEASIBLE_CANDIDATE_SELECTED_FOR_PREFLIGHT_REVIEW`.
- Fresh AVAX operator review: `false_negative_operator_review_avax_sell_cap_feasible_20260625T214943Z.json`, sha `3e7cbb774cb351eb184f5aea07d8f723abcf69132d423ba0a74397c792037b9b`, status `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT`.
- Stale AVAX lower-price reroute: `bounded_probe_lower_price_reroute_review_latest.json`, sha `fcd7f92563dcb1384f6a35f98b6c38cdc21e612c0920e7e3e618aedb5ac3390b`, generated `2026-06-24T17:32:23.429220+00:00`, age about `29.4h`.
- Latest learning chain drift: `autonomous_parameter_proposal_latest.json` and `false_negative_bounded_probe_preflight_latest.json` select `grid_trading|ETHUSDT|Buy`, not AVAX.
- Latest order-to-fill gap: `demo_order_to_fill_gap_latest.json`, sha `c1d430adc12eead29e227c843ccc86a083d05a76a2d1bba2379be292ec383fdc`, status summary `FILL_FLOW_PRESENT`, but `grid_trading|AVAXUSDT|Sell` has `0` candidate-reviewed orders. AVAX rows are `flash_dip_buy|AVAXUSDT|Buy` and risk-close `AVAXUSDT|Sell`, so they cannot satisfy AVAX bounded-probe proof.

## Anti-Repeat Decision

- New evidence delta existed: runtime artifacts changed since the previous report and showed fresh ETH latest-chain artifacts plus fresh AVAX selection/operator-review artifacts.
- The current blocker is not already completed, but rerunning a quote or generating a knowingly blocked reroute artifact would not add decision-quality evidence.
- Decision: `DONE_WITH_CONCERNS`; advance to a source-only blocker.

## Why The Chain Cannot Be Refreshed Now

`bounded_probe_lower_price_reroute_review.py` requires all of these to be fresh and candidate-aligned:

- order construction repair
- false-negative preflight
- false-negative operator review
- placement repair plan
- operator authorization review packet with no emitted authority object
- authority patch readiness
- touchability preflight

Current runtime state does not satisfy that contract. The AVAX reroute artifact is stale; the fresh latest proposal/preflight/placement/authorization/touchability artifacts select ETH; and current AVAX touchability evidence is not candidate-matched to `grid_trading|AVAXUSDT|Sell`.

## Action Taken

- No Bybit call.
- No private/auth endpoint.
- No order/cancel/modify.
- No PG write.
- No `_latest` runtime artifact overwrite.
- No service/env/crontab/runtime mutation.
- No Cost Gate lowering, cap widening, or freshness-gate widening.
- No probe/order/live authority.
- Updated `TODO.md` to the active-dispatch format required by `docs/agents/todo-maintenance.md`.
- Added this PM checkpoint report.

## Aggressive Profit Hypotheses

| Hypothesis | Why it might make money | Fastest safe test | Required data | Failure condition | Authority | Score |
|---|---|---|---|---|---|---|
| Candidate-scoped AVAX false-negative chain | AVAX rank 2 has `73.5511bps` avg net and `48/48` net-positive outcomes, while ETH is cap-blocked. | Source-only AVAX-specific proposal/preflight/touchability/placement/readiness/reroute chain; then one reviewed quote->preview. | Fresh false-negative packet, AVAX selection, candidate-matched touchability or near-touch design proof. | Chain remains candidate-mismatched, stale, or lacks candidate-matched touchability. | Source-only now; E3/BB for later quote. | upside high; evidence medium; realism medium; cost good; time medium; account risk low; governance risk low; autonomy high |
| Maker/MM repeat-window filter | Fee-aware maker cells may survive current fees through maker ratio and adverse-selection control. | Source-only repeat-window scorecard hardening; wait for independent sample. | MM current-fee history, fill_sim windows, maker fee assumptions. | Single-window only or net edge disappears after current fees. | None until proposal. | upside medium; evidence low-medium; realism medium; cost medium; time medium; account risk low; governance risk low; autonomy medium |
| Regime-specific false-negative subset | Broad strategy families may be structurally negative, but narrow regimes/horizons may survive costs. | Build matched-control rows and execution-realism filters from existing artifacts. | Blocked outcomes, controls, regime tags, fills/slippage estimates. | Edge only exists in survivor/stale/replay data. | Source-only. | upside medium-high; evidence medium; realism medium; cost medium; time medium; account risk low; governance risk low; autonomy high |

## Boundary

This checkpoint is docs-only. It does not grant operational authority and does not claim profitability.
