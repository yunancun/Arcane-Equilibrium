# Xuanheng TODO - Active Dispatch Queue

**Version** v546 | **Date** 2026-06-26
**Repo/runtime pointer**: Mac/origin `main` was clean at docs checkpoint `bde6b1a18f4383a42be6245b993ca3fc4ce050d9` before this docs checkpoint. Linux runtime `trade-core` remains source-clean at runtime code checkpoint `0246b26361e403e6cb1ddd126eba8e3cd7b91a23`.
**Current posture**: `P1-AGGRESSIVE-ALPHA-FALSE-NEGATIVE-SUBSET-MINING-NO-ORDER` is closed `DONE_WITH_CONCERNS`. ETH Buy is the highest-upside source-only subset but is not constructible under the current `10 USDT` cap; next executable blocker is `P1-AGGRESSIVE-ALPHA-ETH-BUY-CAP-FEASIBILITY-PROPOSAL-NO-ORDER`.
**Links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--false_negative_subset_mining_eth_cap_bound_no_order.md`; version changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime hygiene | `2026-06-26T04:34:19Z` post-alignment packet is `RUNTIME_HEALTH_HYGIENE_CLEAN_SOURCE_ONLY`; source/crontab/API/artifact compatibility clean; all mutation/authority/proof answers false/NONE. | Hygiene false blockers are closed. This is not profit/probe proof and grants no authority. |
| Runtime source/services | Linux runtime source is clean at `0246b26361e403e6cb1ddd126eba8e3cd7b91a23`; crontab expected-head pins match; user API/watchdog services are active/enabled per hygiene report. | Do not repeat [68], runtime sync, crontab alignment, or hygiene snapshot without new source/crontab/service/artifact delta. |
| False-negative scorecard | `2026-06-26T04:30:54Z` scorecard is `FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY` with `10` ranked candidates and all authority/proof answers false. | Source-only mining found ETH Buy high-upside but cap-bound; AVAX remains current-cap feasible. |
| ETH Buy subset | `grid_trading|ETHUSDT|Buy`, 60m, avg modeled net `258.3905bps`, `7/7` net-positive, friction rank `1`, preflight ready. Current `10 USDT` cap blocks construction: min executable notional about `15.7318 USDT`, rounded qty `0`. | Next safe action is source-only cap/risk feasibility proposal. Do not raise caps or create orders automatically. |
| AVAX bounded candidate | `grid_trading|AVAXUSDT|Sell`, 60m, avg modeled net `73.5511bps`, `48/48` net-positive, cap `10 USDT`, min notional `5 USDT`, current-cap feasible. | Remains the only current cap-feasible bounded Demo candidate, still blocked by authorization. |
| Proof exclusions | `flash_dip_buy`, cleanup/risk-close, unattributed fills, local stale rows, artifact counts, source-smoke, single-window MM positives, replay-only results. | Never count these as bounded-probe proof, Cost Gate proof, promotion evidence, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T045122Z_false_negative_subset_mining_no_order.json` |
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-FALSE-NEGATIVE-SUBSET-MINING-NO-ORDER` |
| `blocker_goal` | Mine latest false-negative scorecard for one review-only high-upside subset/proposal while P0 bounded authorization remains blocked. |
| `profit_relevance` | Identifies high-upside false-negative subsets that may become bounded Demo candidates only after cap/risk/authorization gates. |
| `previous_evidence_checked` | Reports `2026-06-24--false_negative_candidate_friction_scorecard.md`, `2026-06-26--bounded_probe_authorization_antirepeat_todo_hygiene.md`, `2026-06-26--profit_candidate_selection_avax_review_packet.md`; runtime scorecard/cap artifacts. |
| `new_evidence_delta_required` | Fresh/current scorecard evidence sufficient to produce a distinct source-only subset proposal without repeating candidate selection or authorization audit. |
| `new_evidence_delta_found` | ETH Buy is highest-upside measured-friction candidate, but cap screen excludes it under current `10 USDT` cap; AVAX remains top cap-feasible candidate. |
| `anti_repeat_decision` | Distinct source-only alpha subset mining. Did not repeat P0 auth or P0 candidate selection. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P1-AGGRESSIVE-ALPHA-ETH-BUY-CAP-FEASIBILITY-PROPOSAL-NO-ORDER` |
| `why_not_repeating_current_blocker` | Current blocker produced a concrete review-only subset packet; repeating without new scorecard/cap metadata would violate anti-repeat. |

## §2 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE_WITH_CONCERNS | PM -> E3/BB/QC -> PM | Demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; proof exclusions carried in §0/§4. | No-repeat unless new exchange inventory, fills attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE_WITH_CONCERNS | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority. | `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading|AVAXUSDT|Sell`. | No-repeat unless new candidate/cap/fee/touchability evidence appears. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED_BY_RUNTIME_AUTHORIZATION | PM -> E3 -> BB -> PM | Candidate-specific bounded Demo auth only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless valid authorization is admitted and E3/BB review passes. | `2026-06-26--bounded_probe_authorization_antirepeat_todo_hygiene.md`; runtime latest defer-only and candidate-mismatched. | Resume only if valid AVAX scoped auth appears; otherwise stay source-only. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Wait condition: only after authorized bounded Demo probe with candidate-matched outcomes. |
| `P1-AGGRESSIVE-ALPHA-FALSE-NEGATIVE-SUBSET-MINING-NO-ORDER` | 1 | DONE_WITH_CONCERNS | PM -> PM-local synthesis | Exactly one review-only subset/proposal; no orders, no authority, no Cost Gate lowering. | `2026-06-26--false_negative_subset_mining_eth_cap_bound_no_order.md`; ETH Buy selected as source-only cap-bound subset. | No-repeat unless scorecard/cap/preflight evidence changes. |
| `P1-AGGRESSIVE-ALPHA-ETH-BUY-CAP-FEASIBILITY-PROPOSAL-NO-ORDER` | 1 | ACTIVE | PM -> QC -> MIT -> PM | Decide whether ETH Buy's min executable notional can fit an operator/QC-defined bounded Demo risk envelope; no cap mutation, no order/probe authority. | ETH Buy needs about `15.7318 USDT` minimum executable notional vs current `10 USDT` cap. | Build a source-only cap/risk proposal. If rejected, keep AVAX path and mine next cap-feasible filter. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | DONE / NO-OP_ALREADY_DONE | PM -> PA/CC -> PM | Durable learning SSOT selected. | `2026-06-24--learning_ssot_decision_packet.md`; artifact `probe_ledger.jsonl` remains current SSOT. | No-repeat unless SSOT evidence changes. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | DONE / NO-OP_ALREADY_DONE | PM -> PA/E1 -> E2 -> E4 -> PM | Learning output becomes reviewable proposal only; no direct order/risk/live mutation. | `2026-06-24--autonomous_parameter_proposal_contract.md`. | No-repeat unless proposal contract evidence changes. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | DONE_WITH_CONCERNS / NO-OP_ALREADY_DONE | PM -> E3 -> PM | [68], runtime sync, crontab expected-head, and post-alignment hygiene closed without authority/proof contamination. | `2026-06-26--runtime_health_hygiene_post_alignment_snapshot.md`. | No-repeat unless source/crontab/user-service/artifact evidence changes. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | DEFERRED | PM -> BB/E2/E4 -> PM | Production full-scan pagination adoption path recorded and reviewed. | Mac source has helper; no exchange-facing use authorized here. | Carry into future exchange-inventory/reconciler blocker only if needed. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Authorization | Any move from defer/review to bounded Demo grant requires candidate-scoped structured auth or exact typed confirm plus fresh E3/BB review. |
| Runtime/order path | Any Bybit call, adapter/writer enablement, plan mutation, or order submission requires PM -> E3 -> BB -> PM. No current authority exists. |
| Cost Gate | Global Cost Gate must not be lowered. Proof must be candidate-matched and include fills, fees, slippage, lineage, controls, and execution realism. |
| Cap/risk envelope | ETH Buy cap feasibility may be proposed only source-only. Any cap change requires operator/QC-defined bounded risk review and must not mutate runtime automatically. |
| Live/mainnet | Out of scope; no live/mainnet authority. |
| Runtime mutation | Source sync, crontab/env edits, service restart/rebuild/daemon-reload, and PG writes require a separate reviewed blocker. |

## §4 Safety Invariants And Proof Exclusions

- Profit is optimized only inside survival, Guardian/risk gates, Decision Lease, Rust authority, authorization gates, auditability, and reconstructability.
- Learning output may become a reviewable proposal only; it must not directly mutate order/risk/live state.
- Exclude from proof: `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale Working rows, artifact counts, source-smoke, single-window MM positives, and replay-only results.

## §5 Aggressive Alpha Backlog

| Hypothesis | Score snapshot | Fastest safe test | Authority |
|---|---|---|---|
| ETH Buy min-notional cap feasibility | upside High; evidence Medium-Low; realism Medium; cost Good; time Fast; account risk None source-only; governance Low now, Medium if cap changes; autonomy High | QC/MIT source-only cap/risk proposal for min executable notional around `15.73 USDT`. | Research now; operator/QC cap review before any cap envelope; E3/BB + bounded auth before order. |
| AVAX near-touch bounded Demo after valid auth | upside High; evidence Medium; realism Medium; cost Good; time Fast after auth; account risk Low if capped; governance Medium; autonomy High | After valid AVAX auth plus E3/BB: one capped post-only near-touch-or-skip attempt. | Structured bounded Demo authorization + E3/BB required. |
| Cap-feasible low-price false-negative basket | upside Medium; evidence Medium; realism Medium; cost Mixed; time Medium; account risk None source-only; governance Low; autonomy Medium | Source-only regime/filter split over ETC/SUI/FIL/APT/UNI/XRP/OP cap-feasible rows. | Research/proposal only. |

## §6 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--false_negative_subset_mining_eth_cap_bound_no_order.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T045122Z_false_negative_subset_mining_no_order.json | sed -n '1,220p'
ssh trade-core 'jq "{status, generated_at_utc, ranked_candidate_count: (.ranked_candidates|length), top: .ranked_candidates[0:2]}" /tmp/openclaw/cost_gate_learning_lane/false_negative_candidate_friction_scorecard_latest.json'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
