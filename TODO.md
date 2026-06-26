# Xuanheng TODO - Active Dispatch Queue

**Version** v557 | **Date** 2026-06-26
**Repo/runtime pointer**: Local/origin include this docs-only checkpoint above runtime code head; Linux runtime source/crontab expected-head pins are aligned at code checkpoint `99d3b8f7ff50439eee1a3d7e8219b805a303520b`.
**Current posture**: `P1-RUNTIME-HEALTH-HYGIENE-AUTH-STATUS-CLARITY-SYNC-REVIEW` is closed. Actual `P0-BOUNDED-PROBE-AUTHORIZATION` remains blocked by candidate-scoped false-negative preflight/operator authorization gates and has no probe/order authority.
**Links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--authorization_gate_status_clarity_runtime_sync.md`; version changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source/services | `2026-06-26T06:52:53Z` PM/E3 sync put Linux runtime source and crontab expected-head pins at `99d3b8f7ff50439eee1a3d7e8219b805a303520b`; crontab old/new literal counts `0/11`, line count `70`; API MainPID `2218842` stayed active. | v556 authorization-status clarity source is active for future scheduled cron outputs. This was not a service restart, manual cron run, artifact refresh, or authority grant. |
| AVAX bounded candidate | Current selected bounded Demo candidate remains `grid_trading|AVAXUSDT|Sell`, 60m, current-cap feasible, `73.5511bps`, `48/48` positive. | Candidate selection is closed; do not replace AVAX without reopening P0 candidate selection. |
| Latest AVAX artifact chain | Fresh `08:29/08:30 CEST` runtime chain is AVAX-scoped: false-negative review sha `951ab7a9...`, false-negative preflight sha `60af69ad...`, bounded auth sha `4d86859c...`. | Routing fix is proven, but this is not authority or profit proof. |
| Authorization | Runtime latest auth is still defer/no-authority: no emitted object, no `authorization_id`, no standing auth, `active_runtime_probe_authority=false`, `active_runtime_order_authority=false`. | P0 authorization remains blocked. Do not rerun read-only authorization audit without a new candidate-scoped auth delta. |
| v556/v557 status clarity | Runtime source now classifies false-negative preflight blockers as `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED` / `FALSE_NEGATIVE_PREFLIGHT_NOT_READY` instead of misleading sealed-horizon status. | This improves queue/actionability labeling only; it grants no authority and does not refresh existing `_latest` artifacts. |
| ETH cap lead | ETH Buy remains high-upside research-only: current `10 USDT` cap cannot construct it (`15.7105 USDT` min executable notional, rounded qty `0`). | Do not raise cap or route ETH bounded auth without a new QC/operator/E3/BB cap-envelope path. |
| Proof exclusions | Exclude `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale `Working` rows, artifact counts, source-smoke, single-window MM positives, and replay-only results. | Never count these for bounded-probe proof, Cost Gate proof, promotion, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T065019Z_auth_status_clarity_runtime_sync_review.json` |
| `active_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-AUTH-STATUS-CLARITY-SYNC-REVIEW` |
| `blocker_goal` | Sync v556 authorization gate status clarity source to Linux runtime and align expected-head pins without service restart, manual cron, PG write, Bybit call, Cost Gate/risk/cap mutation, or authority grant. |
| `profit_relevance` | Makes the runtime learning lane report the exact false-negative operator-review blocker, reducing wasted authorization loops before bounded Demo PnL proof can exist. |
| `previous_evidence_checked` | v556 source fix report; runtime precheck showing clean `785a4346` checkout and fetched `origin/main=99d3b8f7`; crontab old literal count `11`. |
| `new_evidence_delta_required` | Runtime source/crontab evidence showing v556 was not active on Linux but could be fast-forwarded safely. |
| `new_evidence_delta_found` | Runtime was clean and fast-forwardable; expected-head pins were stale (`old=11`, `new=0`) before sync. |
| `anti_repeat_decision` | Sync runtime source/pins only; do not repeat source fix or P0 authorization read-only audit. |
| `loop_status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION` |
| `why_not_repeating_current_blocker` | Runtime sync and tests are complete; rerunning it without source/runtime drift would be anti-repeat noise. |

## §2 Active Dispatch Queue

| ID | P | Status | Loop decision | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> E3/BB/QC -> PM | Demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; §0 proof exclusions. | No-repeat unless exchange inventory, fill attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority. | `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading|AVAXUSDT|Sell`. | No-repeat unless fresh evidence invalidates AVAX cap feasibility or ranking. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | `BLOCKED_BY_OPERATOR_ACTION` / `BLOCKED_BY_RUNTIME_AUTHORIZATION` | PM -> E3 -> BB -> PM | Candidate-specific bounded Demo auth only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless valid scoped authorization is admitted and E3/BB review passes. | Runtime auth sha `4d86859c...` is defer/no-authority; exact false-negative and bounded-auth confirms are absent; standing auth absent. | No read-only repeat. Resume only on candidate-scoped typed-confirm/standing-auth/authority artifact delta. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | `WAITING_FOR_AUTHORIZED_OUTCOMES` | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Wait until an authorized bounded Demo probe has candidate-matched outcomes. |
| `P1-AUTHORIZATION-GATE-STATUS-CLARITY-SOURCE-FIX` | 1 | DONE | `DONE_WITH_CONCERNS` | PM-local PA/E1/E2/E4/QA equivalent | False-negative preflight/operator-review blocker is labeled accurately; fail-closed tests prove no authority object or runtime probe/order authority. | v556 source tests: auth `19 passed`, scorecard `18 passed`, discovery focused `6 passed`, `py_compile`, `git diff --check`. | No-repeat unless auth schema/status contracts change. |
| `P1-RUNTIME-HEALTH-HYGIENE-AUTH-STATUS-CLARITY-SYNC-REVIEW` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> E3 -> PM | Sync v556 source to Linux and expected-head pins without service restart, manual cron, PG write, Bybit call, Cost Gate/risk/cap mutation, or authority grant. | `2026-06-26--authorization_gate_status_clarity_runtime_sync.md`; runtime `HEAD=origin/main=99d3b8f7`, crontab old/new literals `0/11`, API MainPID unchanged, focused runtime tests `19+18+6 passed`. | No-repeat unless runtime source/crontab drifts again. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Survival/risk | Profit is optimized only inside survival, Guardian/risk, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| Authorization | Demo API permission is not live/mainnet permission. Bounded Demo grant requires candidate-scoped structured auth or exact typed confirm plus E3/BB review. |
| Runtime/order path | Any Bybit private/trading call, adapter/writer enablement, plan mutation, order submission, PG write, crontab/env edit, or service restart requires its reviewed runtime chain. |
| Cost Gate | Global Cost Gate must not be lowered. Proof must be candidate-matched and include fills, fees, slippage, lineage, controls, and execution realism. |
| Candidate selection | AVAX remains the P0 bounded candidate. SUI/FIL are research controls only; ETH is cap-infeasible under current envelope. |
| Live/mainnet | Out of scope; no live/mainnet authority. |

## §4 Aggressive Alpha Backlog

| Hypothesis | Score snapshot | Fastest safe test | Authority |
|---|---|---|---|
| AVAX candidate-scoped authorization admission | upside High path-enabler; evidence High for AVAX route; realism blocked by auth; cost unchanged; time Fast if valid scoped auth appears; account risk None now; governance Medium; autonomy High | Review only a new candidate-scoped auth artifact delta. | Requires typed-confirm/standing-auth evidence and E3/BB review; no order authority now. |
| AVAX first-attempt near-touch design | upside Medium-High; evidence Medium; realism pending; cost model good; time Medium; account risk None now; governance Low; autonomy Medium | Source-only review of near-touch/skip placement design after authorization gate is satisfied. | Design/proposal only until auth exists. |
| ETH high-edge cap-envelope research | upside High if cap envelope exists; evidence Low-Medium; realism Low under current cap; cost good; time Medium; account risk None now; governance Medium; autonomy Medium | Source-only cap sensitivity packet using construction preview + fee/slippage assumptions. | Research only; future cap change needs QC/operator/E3/BB. |

## §5 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--authorization_gate_status_clarity_runtime_sync.md
python3 -m pytest -q /Users/ncyu/Projects/TradeBot/srv/helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py
python3 -m pytest -q /Users/ncyu/Projects/TradeBot/srv/helper_scripts/research/tests/test_profitability_path_scorecard.py
python3 -m pytest -q /Users/ncyu/Projects/TradeBot/srv/helper_scripts/research/tests/test_alpha_discovery_throughput.py -k 'bounded_probe_operator_authorization or profitability_closure or runtime_killboard'
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T065019Z_auth_status_clarity_runtime_sync_review.json | sed -n '1,220p'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
**Self-check**: A next PM can identify the next action in under one minute: stop at P0 authorization until a real candidate-scoped auth delta exists; do not rerun source fix, runtime sync, or read-only auth audit without new evidence.
