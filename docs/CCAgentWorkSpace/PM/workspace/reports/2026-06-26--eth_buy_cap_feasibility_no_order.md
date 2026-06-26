# ETH Buy Cap Feasibility No-Order Decision

Date: 2026-06-26 07:04 CEST

## Required Round Output

| Field | Value |
|---|---|
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-ETH-BUY-CAP-FEASIBILITY-PROPOSAL-NO-ORDER` |
| `blocker_goal` | Decide whether `grid_trading|ETHUSDT|Buy` can fit a bounded Demo cap/risk envelope without mutating cap, risk, runtime, order, or Cost Gate state. |
| `profit_relevance` | ETH Buy is the strongest modeled false-negative lead, but only matters if it can later become a realistic, auditable, risk-bounded Demo test. |
| `constraints_checked` | No global Cost Gate lowering, no live promotion, no Bybit order/cancel/modify, no PG write, no runtime/env/crontab/service mutation, no Rust writer/adapter enablement, no order/probe authority, no proof claim. |
| `previous_evidence_checked` | Prior packet `2026-06-26--false_negative_subset_mining_eth_cap_bound_no_order.md`; TODO v546; runtime read-only artifacts listed below. |
| `new_evidence_delta_required` | A distinct cap feasibility decision with QC/MIT review, not another authorization audit or repeated candidate selection. |
| `new_evidence_delta_found` | ETH remains high-upside but non-constructible under the current `10 USDT` cap; AVAX remains current-cap feasible. |
| `anti_repeat_decision` | Proceeded as a distinct source-only cap decision. Do not repeat without fresh scorecard/cap/construction evidence or a real cap-envelope authorization delta. |
| `action_taken_or_noop_reason` | Rejected/deferred ETH cap expansion now; preserved `10 USDT` cap and no-order posture; moved next work to cap-feasible low-price regime/filter mining after operator pause. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P1-AGGRESSIVE-ALPHA-CAP-FEASIBLE-LOW-PRICE-REGIME-FILTER-NO-ORDER` |
| `why_not_repeating_current_blocker` | The cap feasibility answer is now explicit: no cap mutation and no ETH order path on current evidence. Repeating would only restate the same cap block. |

## Evidence

Runtime read-only hash check was performed only to improve reconstructability. It did not write runtime state or generate/overwrite runtime artifacts.

| Artifact | Status | SHA256 |
|---|---|---|
| `false_negative_candidate_friction_scorecard_latest.json` | `FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY`, generated `2026-06-26T04:30:54.770899Z` | `0d01ca3d9a93ca2178e1fbb486116394bfe89eb9423a9862ddfa6fc830eaa0f7` |
| `false_negative_bounded_probe_preflight_latest.json` | `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION`, generated `2026-06-26T04:29:22.393079Z` | `63fc87f40cd41f8e0983b33aec2d6e87d157aeacd88b4c0527d5bd4ad2f0593f` |
| `bounded_probe_operator_authorization_latest.json` | `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, generated `2026-06-26T05:00:04.766781Z` | `dafee25c768d5d0e0c1b6fcdddb4e34a4cca43592cd61f62f234397edce4e1c2` |
| `bounded_probe_candidate_construction_preview_eth_buy_latest.json` | `CANDIDATE_CONSTRUCTION_NOT_FEASIBLE_UNDER_CAP`, generated `2026-06-25T21:33:34.493816Z` | `f4e36f149bd98d93f2d187fb8650c38038b46e2f3e024df864714f7dce7de9a8` |
| `candidate_universe_instrument_screen_false_negative_cap_feasible_20260625T214943Z.json` | Top current-cap fit is `grid_trading|AVAXUSDT|Sell` | `09627dcd46526e7c15d1084883aa034fa6bc2e0323667206f2ef59bdefa83ecb` |
| `cap_feasible_candidate_selection_avax_sell_20260625T214943Z.json` | `CAP_FEASIBLE_CANDIDATE_SELECTED_FOR_PREFLIGHT_REVIEW` | `909651b8428c0903b7d0e415b17e65cec6f95d2f73fde6e7290a87fd49c9d01e` |

ETH Buy construction evidence:

| Field | Value |
|---|---|
| candidate | `grid_trading|ETHUSDT|Buy`, 60m |
| modeled scorecard signal | `258.3905bps` avg net, `7/7` positive, friction rank `1` |
| current cap | `10.0 USDT` |
| current min executable notional | `15.7105 USDT` |
| rounded quantity under cap | `0.0` |
| blocking gates | `min_positive_qty_notional_exceeds_cap`, `rounded_notional_below_min_notional`, `rounded_qty_not_positive_under_cap` |

AVAX fallback evidence:

| Field | Value |
|---|---|
| candidate | `grid_trading|AVAXUSDT|Sell`, 60m |
| modeled scorecard signal | `73.5511bps` avg net, `48/48` positive |
| current cap feasibility | fits `10 USDT` cap; min positive qty notional `0.6209 USDT`; min notional `5.0 USDT` |
| authority state | still review/defer only; no probe/order/live authority |

## QC / MIT Result

- QC verdict: `DONE_WITH_CONCERNS`. ETH Buy is a valid research lead, but not execution-eligible. Any per-order cap rise to around `16 USDT` would require explicit total exposure treatment and fresh PM -> E3 -> BB review before order path.
- MIT verdict: `DONE_WITH_CONCERNS`. Evidence is sufficient for a source-only proposal, not for cap-envelope approval or order/probe review. Reconstructability is improved by this round's runtime hashes, but candidate-matched fills/fees/slippage/controls are still absent.

## Decision

Do not raise the cap for ETH Buy now.

Rationale:

- The current approved bounded cap is `10 USDT`; ETH needs `15.7105 USDT` minimum executable notional under current metadata.
- The evidence is modeled and small-sample: `7` outcomes and `0` candidate-matched fills.
- Latest authorization remains review/defer only.
- A cap increase is not a harmless parameter tweak; it changes per-order and likely portfolio exposure assumptions.
- ETH can stay on the aggressive research watchlist, but not as a bounded Demo order candidate on this evidence.

The fastest safe next action is not another ETH audit. It is source-only mining of the cap-feasible low-price false-negative set to find a higher-realism subgroup that fits the existing `10 USDT` cap.

## Aggressive Profit Hypotheses

| Hypothesis | Scores | Why it might make money | Fastest safe test | Required data | Failure condition | Authority |
|---|---|---|---|---|---|---|
| Cap-feasible low-price false-negative regime/filter split | upside Medium; evidence Medium; realism Medium; cost Mixed; time Fast; account risk None source-only; governance Low; autonomy High | AVAX/ETC/SUI/FIL/APT/UNI/XRP/OP fit the current cap, so a regime split may preserve modeled net edge without cap expansion. | Source-only split by regime, spread, markout, and controls; select at most one review-only proposal. | Cap screen, scorecard rows, fees/slippage, regimes, spread/markout controls. | Net cushion disappears after costs or no subgroup has a reconstructable evidence path. | Research only; E3/BB + bounded auth before any order. |
| AVAX near-touch bounded Demo after valid scoped auth | upside High; evidence Medium; realism Medium; cost Good; time Fast after auth; account risk Low if capped; governance Medium; autonomy High | AVAX is cap-feasible with `73.5511bps` modeled net and `48/48` modeled-positive outcomes. | After valid AVAX auth and E3/BB review, one post-only near-touch-or-skip bounded Demo attempt. | Exact auth, fresh BBO, cap construction, fees/fills/slippage lineage, controls. | No valid auth, stale BBO, taker fill, missing lineage, or net PnL after costs <= 0. | Structured bounded Demo authorization + PM -> E3 -> BB. |
| ETH Buy cap-envelope reconsideration later | upside High; evidence Low-Medium; realism Low now; cost Good modeled; time Medium; account risk None now/Medium if cap changes; governance Medium; autonomy Medium | ETH has the strongest modeled scorecard lead, but needs a larger cap and better proof path. | Fresh no-order construction plus QC/operator cap-envelope review only after stronger evidence. | Fresh metadata/BBO, larger evidence sample, candidate-matched controls, fee/slippage labels, hashes. | Cap increase weakens survival/risk envelope, sample remains too small, or fill realism stays unproven. | Operator/QC cap review first; E3/BB + valid bounded auth before order. |

## Artifact Necessity

Created only the artifacts needed for auditability and handoff:

- updated session state: `/tmp/openclaw/session_loop_state_20260626T045912Z_eth_buy_cap_feasibility_no_order.json`
- this PM report
- one short operator note
- TODO/changelog/worklog/memory updates

No extra research artifact, `_latest` overwrite, runtime job, PG query/write, or order-path artifact was generated.
