# Xuanheng TODO - Active Dispatch Queue

**Version** v553 | **Date** 2026-06-26
**Repo/runtime pointer**: Source/origin/runtime are aligned at `785a434612f82dae57fbe9bdde0f6d22fb331f0f`; crontab expected-head pins also match this runtime checkpoint.
**Current posture**: `P1-RUNTIME-HEALTH-HYGIENE-ALPHA-BOUNDED-CHAIN-STALENESS-GUARD-SYNC-REVIEW` is closed. Next queue entry is fresh post-guard AVAX latest-chain review; P0 bounded authorization remains blocked until an AVAX-scoped defer/no-authority artifact exists.
**Links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--alpha_bounded_chain_guard_runtime_sync.md`; version changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime hygiene | `2026-06-26T04:34:19Z` hygiene packet is `RUNTIME_HEALTH_HYGIENE_CLEAN_SOURCE_ONLY`; source/crontab/API/artifact compatibility clean; all mutation/authority/proof answers false/NONE. | Hygiene false blockers are closed. This is not profit/probe proof and grants no authority. |
| Runtime source/services | `2026-06-26T06:22:54Z` PM/E3 bounded apply fast-forwarded Linux runtime source `b9836224... -> 785a4346...` and replaced exactly 11 crontab expected-head literals; line count stayed `70`; API MainPID `2218842` remained active/running. | The alpha bounded-chain guard is now active for scheduled cron. This was not a service restart, not a manual cron run, and not an artifact/proof refresh. |
| ETH Buy cap feasibility | ETH construction preview sha `f4e36f14...` is `CANDIDATE_CONSTRUCTION_NOT_FEASIBLE_UNDER_CAP`: current cap `10 USDT`, min executable notional `15.7105 USDT`, rounded qty `0`. | Do not raise cap now. No ETH probe/order path unless future QC/operator cap envelope + E3/BB/auth chain exists. |
| AVAX bounded candidate | AVAX remains selected current P0 candidate: `grid_trading|AVAXUSDT|Sell`, 60m, current-cap feasible, `73.5511bps`, `48/48` positive. | Candidate selection is closed. Do not replace with SUI/FIL without reopening P0 candidate selection. |
| Candidate delta selector | v551 runtime sync made cost-gate false-negative review prefer the cap-feasible selected side-cell. Runtime still has one cap-feasible selection artifact, `grid_trading|AVAXUSDT|Sell`, `fits_current_cap=true`. | Cost-gate selector remains the desired AVAX route. Do not replace AVAX with ETH or controls without reopening candidate selection. |
| Alpha bounded-chain staleness | `2026-06-26T06:20:35Z` read-only check found the natural `08:15:04 CEST` alpha downstream auth artifact sha `43b0bc5e...` still targets `grid_trading|ETHUSDT|Buy` because old runtime consumed stale false-negative bounded preflight. | Runtime now has the fail-closed guard. Next proof is a scheduled post-guard artifact delta, not manual cron execution. |
| Cap-feasible controls | v548 filter packet keeps SUI/FIL as source-only controls. ETC/APT rejected for incomplete BBO; UNI/XRP/OP rejected for thin cushion/hit-rate/sample/spread. | SUI/FIL may inform research only; they are not AVAX proof and not bounded candidates. |
| Matched-control proof contract | v549 design packet: future AVAX proof must use same-side-cell blocked controls plus candidate-matched fill lineage. SUI/FIL cross-symbol controls are research-only and cannot count toward bounded-probe proof, Cost Gate proof, promotion, or AVAX PnL proof. | Future outcome review must use existing proof-exclusion/result-review/execution-realism contracts. |
| Authorization | Latest runtime auth sha `43b0bc5e...`, mtime `2026-06-26 08:15:04 +0200`, remains `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, `decision=defer`, candidate `grid_trading|ETHUSDT|Buy`, no emitted object/probe/order authority. | This predates the guard sync and is not AVAX-scoped or executable. P0 authorization remains blocked until a fresh post-guard AVAX-scoped artifact delta exists. |
| Regime evidence | Current scorecard/cap-screen artifacts contain no leak-free regime labels or markout buckets for the cap-feasible split. | Do not claim regime proof. A future regime split needs a separate data-design blocker after a real evidence delta. |
| Proof exclusions | `flash_dip_buy`, cleanup/risk-close, unattributed fills, local stale rows, artifact counts, source-smoke, single-window MM positives, replay-only results. | Never count these as bounded-probe proof, Cost Gate proof, promotion evidence, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T062035Z_alpha_bounded_chain_guard_runtime_sync_review.json` |
| `active_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-ALPHA-BOUNDED-CHAIN-STALENESS-GUARD-SYNC-REVIEW` |
| `blocker_goal` | Sync the validated alpha bounded-chain stale side-cell guard to Linux runtime and align crontab expected-head pins without restart, manual cron run, PG write, Bybit call, artifact overwrite, or authority mutation. |
| `profit_relevance` | Makes the fail-closed stale-side-cell guard active in scheduled alpha cron so AVAX cap-feasible review is not repeatedly displaced by stale ETH bounded preflight artifacts. |
| `previous_evidence_checked` | v552 source-fix report; v551 runtime sync report; `08:15 CEST` alpha artifacts; runtime source/crontab state. |
| `new_evidence_delta_required` | Runtime source/crontab drift from the validated repo guard commit, or fresh alpha artifact evidence proving the stale ETH bounded chain is still active. |
| `new_evidence_delta_found` | Repo/origin `785a4346`; runtime was still `b9836224`; crontab old/new pin counts were `11/0`; `08:15 CEST` alpha auth remained ETH-scoped. |
| `anti_repeat_decision` | Proceed with distinct runtime sync review; do not repeat P0 authorization because latest auth artifact is pre-guard ETH defer/no-authority. |
| `loop_status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION-AVAX-LATEST-CHAIN-REFRESH-REVIEW` |
| `why_not_repeating_current_blocker` | Runtime sync is complete and should not be rerun unless source/crontab drift changes; P0 authorization still lacks a fresh AVAX-scoped artifact. |

## §2 Active Dispatch Queue

| ID | P | Status | Loop decision | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> E3/BB/QC -> PM | Demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; proof exclusions carried in §0/§4. | No-repeat unless new exchange inventory, fill attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority. | `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading|AVAXUSDT|Sell`. | No-repeat unless fresh evidence invalidates AVAX cap feasibility or candidate ranking. |
| `P0-PROFIT-CANDIDATE-SELECTION-DELTA-REFRESH-NO-ORDER` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> PM | Fresh artifact delta handled; source selector prevents cap-infeasible top false-negative from overriding cap-feasible selected candidate; no authority. | `2026-06-26--candidate_selection_delta_cap_feasible_selector_source_fix.md`; validation: cron static `15`, auth/preflight `23`, policy focused `8`. | No-repeat unless new scorecard/cap/selector evidence changes. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | `BLOCKED_BY_RUNTIME_AUTHORIZATION` | PM -> E3 -> BB -> PM | Candidate-specific bounded Demo auth only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless valid authorization is admitted and E3/BB review passes. | Latest auth sha `43b0bc5e...` is pre-guard defer/review-only and still ETH-scoped; no AVAX-scoped authority. | No-repeat until a fresh post-guard AVAX-scoped authorization artifact exists. |
| `P0-BOUNDED-PROBE-AUTHORIZATION-AVAX-LATEST-CHAIN-REFRESH-REVIEW` | 0 | WAITING | `WAITING_FOR_POST_GUARD_ARTIFACT_DELTA` | PM -> E3 -> BB -> PM if exchange-facing | Review a fresh post-guard AVAX-scoped bounded auth chain for defer/no-authority semantics and hard-boundary preservation; do not grant order/probe authority. | Runtime guard synced at `2026-06-26T06:22:54Z`; latest auth artifact mtime `2026-06-26 08:15:04 +0200` predates the sync and is ETH-scoped. | Scheduled review after the next cost-gate/alpha cron window (`27/30 * * * *`, first expected post-guard chain around `2026-06-26 08:30 CEST`; review around `08:35 CEST`). |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | `WAITING_FOR_AUTHORIZED_OUTCOMES` | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Wait condition: only after authorized bounded Demo probe with candidate-matched outcomes. |
| `P1-AGGRESSIVE-ALPHA-ETH-BUY-CAP-FEASIBILITY-PROPOSAL-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> QC -> MIT -> PM | Source-only cap decision recorded; no cap mutation, no order/probe authority. | `2026-06-26--eth_buy_cap_feasibility_no_order.md`; ETH needs `15.7105 USDT` vs current `10 USDT` cap. | No-repeat unless fresh cap envelope, scorecard, construction, or authorization evidence changes. |
| `P1-AGGRESSIVE-ALPHA-CAP-FEASIBLE-LOW-PRICE-REGIME-FILTER-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM-local synthesis | One source-only filter proposal; no order/probe authority and no candidate replacement. | `2026-06-26--cap_feasible_low_price_filter_no_order.md`; AVAX champion, SUI/FIL controls. | No-repeat unless fresh scorecard/cap-screen/auth/regime evidence changes. |
| `P1-AGGRESSIVE-ALPHA-AVAX-SUI-FIL-MATCHED-CONTROL-DESIGN-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM-local synthesis | Source-only matched-control contract recorded; no order/probe authority and no proof contamination. | `2026-06-26--avax_sui_fil_matched_control_design_no_order.md`; SUI/FIL research-only, not proof. | No-repeat unless source contract, outcome, or control evidence changes. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | DONE | `NO-OP_ALREADY_DONE` | PM -> PA/CC -> PM | Durable learning SSOT selected. | `2026-06-24--learning_ssot_decision_packet.md`; artifact `probe_ledger.jsonl` remains current SSOT. | No-repeat unless SSOT evidence changes. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | DONE | `NO-OP_ALREADY_DONE` | PM -> PA/E1 -> E2 -> E4 -> PM | Learning output becomes reviewable proposal only; no direct order/risk/live mutation. | `2026-06-24--autonomous_parameter_proposal_contract.md`. | No-repeat unless proposal contract evidence changes. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | DONE | `NO-OP_ALREADY_DONE` | PM -> E3 -> PM | Runtime source/crontab/API hygiene closed without authority/proof contamination. | `2026-06-26--runtime_health_hygiene_post_alignment_snapshot.md`. | No-repeat unless source/crontab/user-service/artifact evidence changes. |
| `P1-RUNTIME-HEALTH-HYGIENE-CAP-FEASIBLE-SELECTOR-SYNC-REVIEW` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> E3 -> PM | Sync v550 source fix to Linux and align expected-head pins without service restart, PG write, Bybit call, artifact refresh, or authority mutation. | `2026-06-26--cap_feasible_selector_runtime_sync.md`; historical checkpoint superseded by v553 runtime head `785a4346`. | No-repeat unless runtime source/crontab drifts again. |
| `P1-RUNTIME-HEALTH-HYGIENE-ALPHA-BOUNDED-CHAIN-STALENESS-GUARD-SOURCE-FIX` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Alpha cron fails closed when cap-feasible selected side-cell mismatches bounded preflight; stale bounded artifacts are not refreshed or passed into scorecard. | `2026-06-26--alpha_bounded_chain_stale_side_cell_guard_source_fix.md`; validation: bash syntax PASS, alpha cron static `9 passed`, cost-gate cron static `15 passed`. | No-repeat unless alpha cron source, cap-feasible selection, or bounded preflight schema changes. |
| `P1-RUNTIME-HEALTH-HYGIENE-ALPHA-BOUNDED-CHAIN-STALENESS-GUARD-SYNC-REVIEW` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> E3 -> PM | Sync the source guard to runtime and align expected-head pins without service restart, PG write, Bybit call, manual cron run, `_latest` overwrite, or authority mutation. | `2026-06-26--alpha_bounded_chain_guard_runtime_sync.md`; runtime `HEAD=origin/main=785a4346`, crontab old/new counts `0/11`, API MainPID unchanged, runtime tests `24 passed`. | No-repeat unless runtime source/crontab drifts again. |
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
| AVAX post-guard latest-chain alignment | upside High path-enabler; evidence Medium; realism pending fresh artifact; cost model good; time Fast next cron; account risk None now; governance Low; autonomy High | Review the first post-guard cost-gate/alpha artifact chain for AVAX scope and no-authority fields. | Artifact review only; no order authority. |
| AVAX alpha bounded-chain stale-side guard | upside High path-enabler; evidence High for bug path; realism runtime-synced; cost model unchanged; time Fast; account risk None now; governance Low; autonomy High | Confirm the next scheduled alpha cycle no longer refreshes stale ETH bounded chain. | Artifact review only; no order authority. |
| ETH high-edge cap-envelope research | upside High if cap envelope exists; evidence Low-Medium; realism Low under current cap; cost model good; time Medium; account risk None now; governance Medium if cap pressure; autonomy Medium | Source-only cap-envelope sensitivity packet; do not route bounded authorization under current `10 USDT` cap. | Research only; future cap change needs QC/operator/E3/BB. |

## §6 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--alpha_bounded_chain_stale_side_cell_guard_source_fix.md
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--alpha_bounded_chain_guard_runtime_sync.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T062035Z_alpha_bounded_chain_guard_runtime_sync_review.json | sed -n '1,220p'
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && git rev-parse HEAD && git status --short --branch; crontab -l | grep -o 785a434612f82dae57fbe9bdde0f6d22fb331f0f | wc -l; stat -c "%y %n" /tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
**Self-check**: §2 uses TODO operational statuses only; loop/state-machine outcomes are preserved separately in `Loop decision`.
