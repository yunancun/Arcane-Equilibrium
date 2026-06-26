# Candidate Source Freshness Alignment + Atomic Preview Runner

1. `active_blocker_id`: `P1-AGGRESSIVE-ALPHA-CANDIDATE-SOURCE-FRESHNESS-ALIGNMENT-NO-CAPTURE`
2. `blocker_goal`: Produce or select a fresh, timestamped, candidate-aligned AVAX reroute/source packet, or fail closed with exact missing gates; no stale `_latest`.
3. `profit_relevance`: Fresh source alignment plus a no-order construction preview makes the AVAX candidate ready for future bounded Demo authorization review without relying on stale artifacts, replay-only results, or non-reconstructable evidence.
4. `constraints_checked`: No private Bybit call; no order submit/cancel/modify; no PG query/write; no runtime/service/env/crontab mutation; no Rust writer/adapter enablement; no global Cost Gate or freshness-gate lowering; no probe/order/live authority grant; no bounded-probe proof, promotion proof, or profit claim.
5. `previous_evidence_checked`: v573 stale `_latest` reroute sha `fcd7f925...`, fresh timestamped alignment-blocked reroute sha `97021201...`, fresh cap-feasible selection, false-negative preflight, demo order-to-fill gap audit, runtime auth sha `61483e69...`, E3/BB reviews, and v570-v573 quote/adapter reports.
6. `new_evidence_delta_required`: A fresh, timestamped AVAX reroute/source packet ready for no-order construction preview, or a fail-closed packet naming the exact stale/alignment gates.
7. `new_evidence_delta_found`: Fresh cap-mapped reroute packet is ready; one reviewed atomic public quote -> adapter -> no-order preview runner produced a ready construction preview with all grant/order/proof flags false.
8. `anti_repeat_decision`: `DONE_WITH_CONCERNS_FRESH_SOURCE_AND_ATOMIC_PREVIEW_READY_NO_ORDER`. Do not repeat source alignment or public quote runner without new source/runtime/artifact delta.
9. `action_taken_or_noop_reason`: Fixed the source handoff bug that omitted `current_cap_usdt` when only `cap_usdt` was present, added an atomic runner so quote freshness does not expire between manual steps, ran one E3/BB-reviewed public quote/adapter/no-order preview, and stopped before any authority/order path.
10. `aggressive_profit_hypotheses`:

| Hypothesis | why_it_might_make_money | fastest_safe_test | required_data | failure_condition | authority_required | max_safe_next_action | Scoring |
|---|---|---|---|---|---|---|---|
| AVAX maker-first bounded Demo micro-probe | Fresh BBO shows AVAX Sell is constructible under the existing `10 USDT` cap with a near-touch sell limit. | Candidate-scoped authorization review only; no order until exact auth object plus E3/BB order-envelope review. | Fresh preview, scoped auth object, Decision Lease/Rust admission, fill/fee/slippage lineage. | No scoped auth, stale BBO, crossing/taker placement, or net PnL after fees/slippage <= 0. | Candidate-scoped bounded Demo authorization plus runtime/order E3/BB. | Keep blocked at P0 auth; do not submit order. | upside High; evidence Medium-High; realism Medium; cost critical; time Medium; account risk bounded; governance High; autonomy High |
| Atomic public quote adapter runner as freshness bridge | Same-process capture -> adapter -> preview avoids stale quote reuse without lowering freshness. | Reuse source/test path on future reviewed candidates; exchange run only after E3/BB. | Fresh source packet, public quote retCode/BBO/instrument fields, adapter provenance, preview status. | Any `_latest` output, wider freshness gate, private/auth endpoint, or preview used as proof/order admission. | E3/BB for each exchange-facing run. | Reuse only with new reviewed source delta. | upside Medium; evidence High; realism High; cost Low; time Fast; account risk None; governance Low; autonomy High |
| Maker spread/cost cushion screen | Tight AVAX spread may allow post-only maker execution to survive fees if fill quality is real. | Source-only fee/maker cushion worksheet from the preview and current fee tier; no order. | Maker fee, slippage buffer, limit/qty/notional, spread, fill-probability proxy. | After-cost cushion <= 0, maker fill probability too low, or taker fallback required. | None for analysis; auth for any order. | Defer until P0 auth or explicit source-only worksheet request. | upside Medium; evidence Medium; realism Medium; cost High impact; time Fast; account risk None; governance Low; autonomy Medium |

11. `status`: `DONE_WITH_CONCERNS`
12. `next_blocker_id`: `P0-BOUNDED-PROBE-AUTHORIZATION`
13. `why_not_repeating_current_blocker`: The blocker has a fresh cap-mapped source packet and a ready no-order preview. Repeating would only create another non-proof quote/preview artifact without bounded-probe authorization.
14. `branch_commit_push`: Pending at report creation; final PM response records branch, commit SHA, and push status.

## Evidence

| Artifact | Status | SHA256 |
|---|---|---|
| `/tmp/openclaw/candidate_source_freshness_alignment_20260626T102434Z/bounded_probe_lower_price_reroute_review_avax_sell_fresh_aligned_cap_mapped.json` | `LOWER_PRICE_REROUTE_READY_FOR_DEMO_CONSTRUCTION_REVIEW` | `bc300277deab62ac3bf2b07baae28aa7c8d1e0e22ea8669af7f36f9b39e54fcf` |
| `/tmp/openclaw/atomic_quote_adapter_preview_runner_20260626T1045Z/summary.json` | `ATOMIC_QUOTE_ADAPTER_PREVIEW_READY_NO_ORDER` | `98c7d75df9b008657509f84f52520958795ec9deee33de695443978c6e16a0b1` |
| `/tmp/openclaw/atomic_quote_adapter_preview_runner_20260626T1045Z/public_quote.json` | `PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER` | `47fb06632aa62e0c229525d0511dc4dc9dacf949ac9c661015431a4112520aa5` |
| `/tmp/openclaw/atomic_quote_adapter_preview_runner_20260626T1045Z/market_snapshot.json` | `PUBLIC_QUOTE_MARKET_SNAPSHOT_READY_NO_ORDER` | `feccb48ed8de1abf63d5437fed4fb357857dd85c70a97f8f037c6cee2ce7dd72` |
| `/tmp/openclaw/atomic_quote_adapter_preview_runner_20260626T1045Z/construction_preview.json` | `CANDIDATE_CONSTRUCTION_PREVIEW_READY_NO_ORDER` | `f721bc3a810b676f7fa99081e6e126e8b5040561ea10b4fdf9951485e5068cf3` |

Runner public request audit: exactly three unauthenticated public GETs to `https://api.bybit.com/v5/market/time`, `/v5/market/tickers?category=linear&symbol=AVAXUSDT`, and `/v5/market/instruments-info?category=linear&symbol=AVAXUSDT`; each HTTP `200`, retCode `0`, no redirect, `User-Agent` only.

Construction preview: bid/ask `6.145/6.146`, effective BBO age `254.561ms` vs max `1000ms`, spread `1.6272bps`, instrument `Trading`, limit `6.146`, qty `1.6`, notional `9.8336 USDT`, cap `10.0 USDT`, blocking gates `0`.

## Review And Verification

- E2: `DONE`; output containment, fixed freshness gate, fail-closed adapter coverage, and source cap mapping reviewed.
- E4/PM: combined adjacent suite `99 passed`; atomic runner suite `5 passed`; `py_compile` passed; `git diff --check` passed.
- E3: `DONE_WITH_CONCERNS`; cleared exactly one atomic public quote -> adapter -> no-order preview runner under no-auth/no-order/no-mutation constraints.
- BB: `DONE_WITH_CONCERNS`; no Bybit-side blocker for the three public market GETs under the reviewed envelope.
- QA: `DONE_WITH_CONCERNS`; no blocker. Concern recorded that `demo_operational_authorization_available_from_thread: true` appears in construction preview input context, but all actual grant/order/proof flags remain false.

Manual pre-run capture produced a public quote but adapter failed closed with `public_quote_stale_at_adapter_generation`; no second capture was run until the atomic runner had E3/BB review.

## PM Decision

This checkpoint is closed as source/preview `DONE_WITH_CONCERNS`. The next blocker is P0 bounded-probe authorization. Broad Demo API permission does not bypass repo authorization gates; order/probe work needs a candidate-scoped auth object or exact typed confirm plus E3/BB review.
