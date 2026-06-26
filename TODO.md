# Xuanheng TODO - Active Dispatch Queue

**Version** v551 | **Date** 2026-06-26
**Repo/runtime pointer**: Runtime code checkpoint `b983622478d5b9fa05df65a375b1f3ca1ae7fda4` is synced to Linux `trade-core` and crontab expected-head pins match; this TODO/report checkpoint is docs-only above that runtime code head.
**Current posture**: `P1-RUNTIME-HEALTH-HYGIENE-CAP-FEASIBLE-SELECTOR-SYNC-REVIEW` is closed with a no-restart runtime source/crontab sync. Next queue entry is `P0-BOUNDED-PROBE-AUTHORIZATION-AVAX-LATEST-CHAIN-REFRESH-REVIEW`, gated on a post-sync artifact delta.
**Links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--cap_feasible_selector_runtime_sync.md`; version changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime hygiene | `2026-06-26T04:34:19Z` hygiene packet is `RUNTIME_HEALTH_HYGIENE_CLEAN_SOURCE_ONLY`; source/crontab/API/artifact compatibility clean; all mutation/authority/proof answers false/NONE. | Hygiene false blockers are closed. This is not profit/probe proof and grants no authority. |
| Runtime source/services | `2026-06-26T05:50:53Z` PM/E3 bounded apply fast-forwarded Linux runtime source `0246b263... -> b9836224...` and replaced exactly 5 crontab expected-head literals; line count stayed `70`; API MainPID `2218842` remained active/running. | The cap-feasible selector fix is now active for future cron runs. This was not a restart, not a cron run, and not an artifact/proof refresh. |
| ETH Buy cap feasibility | ETH construction preview sha `f4e36f14...` is `CANDIDATE_CONSTRUCTION_NOT_FEASIBLE_UNDER_CAP`: current cap `10 USDT`, min executable notional `15.7105 USDT`, rounded qty `0`. | Do not raise cap now. No ETH probe/order path unless future QC/operator cap envelope + E3/BB/auth chain exists. |
| AVAX bounded candidate | AVAX remains selected current P0 candidate: `grid_trading|AVAXUSDT|Sell`, 60m, current-cap feasible, `73.5511bps`, `48/48` positive. | Candidate selection is closed. Do not replace with SUI/FIL without reopening P0 candidate selection. |
| Candidate delta selector | v551 runtime sync makes cron false-negative operator review prefer explicit/cap-feasible selected side-cell before falling back to top ranked false-negative. Latest auth artifact has not yet refreshed after this sync. | Next authorization review needs a post-sync artifact mtime delta. No authority or proof follows from the sync itself. |
| Cap-feasible controls | v548 filter packet keeps SUI/FIL as source-only controls. ETC/APT rejected for incomplete BBO; UNI/XRP/OP rejected for thin cushion/hit-rate/sample/spread. | SUI/FIL may inform research only; they are not AVAX proof and not bounded candidates. |
| Matched-control proof contract | v549 design packet: future AVAX proof must use same-side-cell blocked controls plus candidate-matched fill lineage. SUI/FIL cross-symbol controls are research-only and cannot count toward bounded-probe proof, Cost Gate proof, promotion, or AVAX PnL proof. | Future outcome review must use existing proof-exclusion/result-review/execution-realism contracts. |
| Authorization | Latest runtime auth sha `cdf20e57...`, mtime `2026-06-26 07:45:04 +0200`, remains `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, `decision=defer`, candidate `grid_trading|ETHUSDT|Buy`, no emitted object/probe/order authority. | `P0-BOUNDED-PROBE-AUTHORIZATION` remains blocked until the first post-sync cron artifact delta can be reviewed for AVAX scope. |
| Regime evidence | Current scorecard/cap-screen artifacts contain no leak-free regime labels or markout buckets for the cap-feasible split. | Do not claim regime proof. A future regime split needs a separate data-design blocker after a real evidence delta. |
| Proof exclusions | `flash_dip_buy`, cleanup/risk-close, unattributed fills, local stale rows, artifact counts, source-smoke, single-window MM positives, replay-only results. | Never count these as bounded-probe proof, Cost Gate proof, promotion evidence, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T054925Z_cap_feasible_selector_runtime_sync_review.json` |
| `active_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-CAP-FEASIBLE-SELECTOR-SYNC-REVIEW` |
| `blocker_goal` | Sync the tested cap-feasible selector fix to Linux runtime and align cron expected-head pins without restart, PG write, Bybit call, artifact refresh, or authority mutation. |
| `profit_relevance` | Lets future cron artifacts route bounded Demo review toward current-cap-feasible AVAX instead of cap-infeasible ETH. |
| `previous_evidence_checked` | v550 report; runtime auth/scorecard artifacts; runtime source/crontab state before sync. |
| `new_evidence_delta_required` | Source/runtime drift where Mac/origin had the tested selector fix and Linux runtime/crontab still pinned the old head. |
| `new_evidence_delta_found` | Mac/origin `b9836224`; Linux runtime and crontab still `0246b263`; fresh 07:45 authorization artifact remained ETH defer/no-authority. |
| `anti_repeat_decision` | Proceed with distinct runtime sync review; do not repeat P0 authorization because no AVAX-scoped post-sync artifact exists yet. |
| `loop_status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION-AVAX-LATEST-CHAIN-REFRESH-REVIEW` |
| `why_not_repeating_current_blocker` | Runtime source/crontab sync is complete and post-check clean; latest auth artifact predates the sync and remains ETH defer/no-authority. |

## §2 Active Dispatch Queue

| ID | P | Status | Loop decision | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> E3/BB/QC -> PM | Demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; proof exclusions carried in §0/§4. | No-repeat unless new exchange inventory, fill attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority. | `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading|AVAXUSDT|Sell`. | No-repeat unless fresh evidence invalidates AVAX cap feasibility or candidate ranking. |
| `P0-PROFIT-CANDIDATE-SELECTION-DELTA-REFRESH-NO-ORDER` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> PM | Fresh artifact delta handled; source selector prevents cap-infeasible top false-negative from overriding cap-feasible selected candidate; no authority. | `2026-06-26--candidate_selection_delta_cap_feasible_selector_source_fix.md`; validation: cron static `15`, auth/preflight `23`, policy focused `8`. | No-repeat unless new scorecard/cap/selector evidence changes. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | `BLOCKED_BY_RUNTIME_AUTHORIZATION` | PM -> E3 -> BB -> PM | Candidate-specific bounded Demo auth only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless valid authorization is admitted and E3/BB review passes. | Latest auth sha `cdf20e57...` is defer/review-only and still ETH-scoped; no AVAX-scoped authority. | No-repeat until a post-sync artifact mtime delta exists. |
| `P0-BOUNDED-PROBE-AUTHORIZATION-AVAX-LATEST-CHAIN-REFRESH-REVIEW` | 0 | WAITING | `WAITING_FOR_POST_SYNC_ARTIFACT_DELTA` | PM -> E3 -> BB -> PM if exchange-facing | Review the first post-`b9836224` cost-gate cron artifact chain for AVAX scope, defer/no-authority semantics, and hard-boundary preservation; do not grant order/probe authority. | Runtime source/crontab synced at `2026-06-26T05:50:53Z`; current auth artifact mtime `2026-06-26 07:45:04 +0200` predates sync. | Scheduled review after the next cost-gate cron run (`27 * * * *`, first expected post-sync run around `2026-06-26 08:27 CEST`; review around `08:35 CEST`). |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | `WAITING_FOR_AUTHORIZED_OUTCOMES` | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Wait condition: only after authorized bounded Demo probe with candidate-matched outcomes. |
| `P1-AGGRESSIVE-ALPHA-ETH-BUY-CAP-FEASIBILITY-PROPOSAL-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> QC -> MIT -> PM | Source-only cap decision recorded; no cap mutation, no order/probe authority. | `2026-06-26--eth_buy_cap_feasibility_no_order.md`; ETH needs `15.7105 USDT` vs current `10 USDT` cap. | No-repeat unless fresh cap envelope, scorecard, construction, or authorization evidence changes. |
| `P1-AGGRESSIVE-ALPHA-CAP-FEASIBLE-LOW-PRICE-REGIME-FILTER-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM-local synthesis | One source-only filter proposal; no order/probe authority and no candidate replacement. | `2026-06-26--cap_feasible_low_price_filter_no_order.md`; AVAX champion, SUI/FIL controls. | No-repeat unless fresh scorecard/cap-screen/auth/regime evidence changes. |
| `P1-AGGRESSIVE-ALPHA-AVAX-SUI-FIL-MATCHED-CONTROL-DESIGN-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM-local synthesis | Source-only matched-control contract recorded; no order/probe authority and no proof contamination. | `2026-06-26--avax_sui_fil_matched_control_design_no_order.md`; SUI/FIL research-only, not proof. | No-repeat unless source contract, outcome, or control evidence changes. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | DONE | `NO-OP_ALREADY_DONE` | PM -> PA/CC -> PM | Durable learning SSOT selected. | `2026-06-24--learning_ssot_decision_packet.md`; artifact `probe_ledger.jsonl` remains current SSOT. | No-repeat unless SSOT evidence changes. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | DONE | `NO-OP_ALREADY_DONE` | PM -> PA/E1 -> E2 -> E4 -> PM | Learning output becomes reviewable proposal only; no direct order/risk/live mutation. | `2026-06-24--autonomous_parameter_proposal_contract.md`. | No-repeat unless proposal contract evidence changes. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | DONE | `NO-OP_ALREADY_DONE` | PM -> E3 -> PM | Runtime source/crontab/API hygiene closed without authority/proof contamination. | `2026-06-26--runtime_health_hygiene_post_alignment_snapshot.md`. | No-repeat unless source/crontab/user-service/artifact evidence changes. |
| `P1-RUNTIME-HEALTH-HYGIENE-CAP-FEASIBLE-SELECTOR-SYNC-REVIEW` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> E3 -> PM | Sync v550 source fix to Linux and align expected-head pins without service restart, PG write, Bybit call, artifact refresh, or authority mutation. | `2026-06-26--cap_feasible_selector_runtime_sync.md`; runtime `HEAD=origin/main=b9836224`, crontab old count `0`, new count `5`, API MainPID unchanged. | No-repeat unless runtime source/crontab drifts again. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | DEFERRED | `DEFERRED` | PM -> BB/E2/E4 -> PM | Production full-scan pagination adoption path recorded and reviewed. | Mac source has helper; no exchange-facing use authorized here. | Carry into future exchange-inventory/reconciler blocker only if needed. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Authorization | Any move from review/defer to bounded Demo grant requires candidate-scoped structured auth or exact typed confirm plus fresh E3/BB review. |
| Runtime/order path | Any Bybit private/trading call, adapter/writer enablement, plan mutation, or order submission requires PM -> E3 -> BB -> PM. |
| Cost Gate | Global Cost Gate must not be lowered. Proof must be candidate-matched and include fills, fees, slippage, lineage, controls, and execution realism. |
| Candidate selection | AVAX remains the selected P0 candidate. SUI/FIL controls cannot become bounded candidates without reopening P0 selection. |
| Cross-symbol controls | SUI/FIL are research-only controls and must not count as AVAX proof, promotion evidence, or Cost Gate proof. |
| Live/mainnet | Out of scope; no live/mainnet authority. |
| Runtime mutation | Source sync, crontab/env edits, service restart/rebuild/daemon-reload, and PG writes require a separate reviewed blocker. |

## §4 Safety Invariants And Proof Exclusions

- Profit is optimized only inside survival, Guardian/risk gates, Decision Lease, Rust authority, authorization gates, auditability, and reconstructability.
- Learning output may become a reviewable proposal only; it must not directly mutate order/risk/live state.
- Exclude from proof: `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale `Working` rows, artifact counts, source-smoke, single-window MM positives, and replay-only results.

## §5 Aggressive Alpha Backlog

| Hypothesis | Score snapshot | Fastest safe test | Authority |
|---|---|---|---|
| AVAX cap-feasible selector path | upside High path-enabler; evidence Medium; realism pending post-sync artifact; cost model good; time Fast after next cron; account risk None now; governance Low; autonomy High | Review the first post-sync cost-gate artifact chain for AVAX scope and no-authority fields. | Artifact review only; no order authority. |
| ETH high-edge cap-envelope research | upside High if cap envelope exists; evidence Low-Medium; realism Low under current cap; cost model good; time Medium; account risk None now; governance Medium if cap pressure; autonomy Medium | Source-only cap-envelope sensitivity packet; do not route bounded authorization under current `10 USDT` cap. | Research only; future cap change needs QC/operator/E3/BB. |
| Horizon-edge amplification path | upside Medium; evidence Low scorecard-only; realism Unknown; cost Unknown; time Medium; account risk None; governance Low; autonomy Medium | Source-only horizon-specific candidate packet after AVAX latest chain is aligned. | Research/proposal only. |

## §6 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--cap_feasible_selector_runtime_sync.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T054925Z_cap_feasible_selector_runtime_sync_review.json | sed -n '1,220p'
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && git rev-parse HEAD && git status --short --branch && stat -c "%y %n" /tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
**Self-check**: §2 uses TODO operational statuses only; loop/state-machine outcomes are preserved separately in `Loop decision`.
