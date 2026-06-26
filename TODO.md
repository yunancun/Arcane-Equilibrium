# Xuanheng TODO - Active Dispatch Queue

**Version** v559 | **Date** 2026-06-26
**Source/runtime pointer**: local source includes v559 cap-envelope evidence-floor patch; Linux runtime code/crontab pins remain `99d3b8f7ff50439eee1a3d7e8219b805a303520b` until a separate runtime sync review.
**Current posture**: v559 closed source-only `P1-AGGRESSIVE-ALPHA-CAP-ENVELOPE-EVIDENCE-FLOOR-SOURCE-ONLY`. `P0-BOUNDED-PROBE-AUTHORIZATION` remains blocked; do not rerun read-only auth audit without a real candidate-scoped auth delta.
**Links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--cap_envelope_evidence_floor_source_patch.md`; version changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source/services | `2026-06-26T07:03:49Z` read-only snapshot: Linux runtime source `99d3b8f7ff50439eee1a3d7e8219b805a303520b`; prior v557 sync left crontab expected-head pins aligned to this code head and API MainPID `2218842`. | Runtime code is intentionally behind docs-only local/origin head. No runtime sync is required for v558 docs/report changes. |
| Artifact SSOT path | Current cost-gate artifacts are under `/tmp/openclaw/cost_gate_learning_lane/`, not `/tmp/openclaw/` root. | Future read-only checks must use the canonical subdirectory or they will falsely report missing latest artifacts. |
| Authorization latest | `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json`, mtime `2026-06-26T07:00:04Z`, sha `c46dcd88...`, status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, candidate `grid_trading|AVAXUSDT|Sell`, decision `defer`, `typed_confirm_matches=false`, no authorization id/object, no probe/order authority. | v557 status clarity is active in scheduled artifacts, but this is not an authorization delta. P0 authorization stays blocked. |
| AVAX bounded candidate | Selected bounded Demo candidate remains `grid_trading|AVAXUSDT|Sell`, 60m, current-cap feasible, modeled `73.5511bps`, `48/48` positive. | Candidate selection is closed. Do not replace AVAX without reopening P0 candidate selection on fresh evidence. |
| ETH cap staircase | ETH Buy remains top modeled false-negative lead, but current `10 USDT` cap cannot construct it. At recorded `1571.05` limit price and `0.01` qty step, first executable tier is `0.01 ETH = 15.7105 USDT`; second is `0.02 ETH = 31.4210 USDT`; third is `0.03 ETH = 47.1315 USDT`. | ETH is research-only. Any future ETH cap envelope is a separate operator/QC/E3/BB review; no cap mutation now. |
| Cap-envelope proposal source | v559 source patch adds `cost_gate_cap_envelope_evidence_floor_v1` into `cost_gate_autonomous_parameter_proposal_v1`; all cap-envelope rows are inactive with `mutation_allowed_by_this_packet=false` and `cap_envelope_mutation_allowed=false`. | Learning output can now carry cap-envelope evidence-floor requirements as a review packet only. Runtime scheduled artifacts will not include this until a separate runtime sync review. |
| Proof exclusions | Exclude `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale `Working` rows, artifact counts, source-smoke, single-window MM positives, and replay-only results. | Never count these for bounded-probe proof, Cost Gate proof, promotion, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T071429Z_cap_envelope_evidence_floor_source_only.json` |
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-CAP-ENVELOPE-EVIDENCE-FLOOR-SOURCE-ONLY` |
| `blocker_goal` | Define and enforce the source-level evidence floor before high-priced/high-upside learned candidates can become cap-envelope proposals. |
| `profit_relevance` | Converts high-upside learning output into reviewable proposal criteria without allowing a hidden cap/exposure increase. |
| `previous_evidence_checked` | v558 ETH cap report; runtime artifact snapshot at `2026-06-26T07:14:29Z`; alpha regime governance audit; P0 cost-wall audit; autonomous proposal/result/proof source contracts. |
| `new_evidence_delta_required` | P0 auth had no real delta, so only a distinct source-only evidence-floor contract could advance the loop. |
| `new_evidence_delta_found` | Existing autonomous proposal lacked reusable cap-envelope floor; source patch now emits `cost_gate_cap_envelope_evidence_floor_v1`. |
| `anti_repeat_decision` | `P0-BOUNDED-PROBE-AUTHORIZATION` = `NO-OP_NO_EVIDENCE_DELTA`; ETH cap sensitivity = `NO-OP_ALREADY_DONE`; source-only evidence-floor patch was distinct. |
| `loop_status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-CAP-ENVELOPE-PROPOSAL-SYNC-REVIEW` if runtime sync is pursued; otherwise P0 authorization remains blocked until real auth delta. |
| `why_not_repeating_current_blocker` | The source contract is present and tested; repeating without runtime sync or new evidence is noise. |

## §2 Active Dispatch Queue

| ID | P | Status | Loop decision | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> E3/BB/QC -> PM | Demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; §0 proof exclusions. | No-repeat unless exchange inventory, fill attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority. | `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading|AVAXUSDT|Sell`. | No-repeat unless fresh evidence invalidates AVAX cap feasibility or ranking. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | `BLOCKED_BY_RUNTIME_AUTHORIZATION` | PM -> E3 -> BB -> PM | Candidate-specific bounded Demo auth only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless valid scoped authorization is admitted and E3/BB review passes. | `2026-06-26T07:00:04Z` auth latest sha `c46dcd88...`: `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, AVAX-scoped, decision `defer`, no typed confirm/object/authority. | No read-only repeat. Resume only on candidate-scoped typed-confirm/standing-auth/authority artifact delta. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | `WAITING_FOR_AUTHORIZED_OUTCOMES` | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Wait until an authorized bounded Demo probe has candidate-matched outcomes. |
| `P1-AUTHORIZATION-GATE-STATUS-CLARITY-SOURCE-FIX` | 1 | DONE | `DONE_WITH_CONCERNS` | PM-local PA/E1/E2/E4/QA equivalent | False-negative preflight/operator-review blocker is labeled accurately; fail-closed tests prove no authority object or runtime probe/order authority. | Commit `99d3b8f7`; auth `19 passed`, scorecard `18 passed`, discovery focused `6 passed`. | No-repeat unless auth schema/status contracts change. |
| `P1-RUNTIME-HEALTH-HYGIENE-AUTH-STATUS-CLARITY-SYNC-REVIEW` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> E3 -> PM | Sync v556 source to Linux and expected-head pins without service restart, manual cron, PG write, Bybit call, Cost Gate/risk/cap mutation, or authority grant. | `2026-06-26--authorization_gate_status_clarity_runtime_sync.md`; runtime code/crontab aligned to `99d3b8f7`. | No-repeat unless runtime source/crontab drifts again. |
| `P1-AGGRESSIVE-ALPHA-ETH-CAP-ENVELOPE-SENSITIVITY-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> QC/MIT-equivalent source review -> PM | ETH cap tiers quantified; no cap mutation; no proof/authority claim; TODO normalized. | `2026-06-26--eth_cap_envelope_sensitivity_no_order.md`; first executable tier `15.7105 USDT`. | No-repeat unless ETH price/metadata/cap/evidence changes. |
| `P1-AGGRESSIVE-ALPHA-CAP-ENVELOPE-EVIDENCE-FLOOR-SOURCE-ONLY` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Autonomous proposal emits cap-envelope evidence floor; no cap mutation or authority; focused/adjacent tests pass. | `2026-06-26--cap_envelope_evidence_floor_source_patch.md`; tests `10 passed`, `py_compile`, `git diff --check`. | No-repeat unless source contract requirements change. |
| `P1-RUNTIME-HEALTH-HYGIENE-CAP-ENVELOPE-PROPOSAL-SYNC-REVIEW` | 1 | DEFERRED | `DEFERRED_RUNTIME_MUTATION_REQUIRES_REVIEW` | PM -> E3 -> PM | If pursued, sync v559 source to Linux and expected-head pins without service restart/manual cron/PG/Bybit/order/authority. | v559 source exists only locally/origin after commit; runtime remains `99d3b8f7`. | Separate runtime sync review only; do not mutate runtime inside source patch checkpoint. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Survival/risk | Profit is optimized only inside survival, Guardian/risk, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| Authorization | Demo API permission is not live/mainnet permission. Bounded Demo grant requires candidate-scoped structured auth or exact typed confirm plus E3/BB review. |
| Runtime/order path | Any Bybit private/trading call, adapter/writer enablement, plan mutation, order submission, PG write, crontab/env edit, or service restart requires its reviewed runtime chain. |
| Cost Gate | Global Cost Gate must not be lowered. Proof must be candidate-matched and include fills, fees, slippage, lineage, controls, and execution realism. |
| Candidate selection | AVAX remains the P0 bounded candidate. ETH is high-upside research-only until a separate cap-envelope review exists. |
| Live/mainnet | Out of scope; no live/mainnet authority. |

## §4 Aggressive Alpha Backlog

| Hypothesis | Score snapshot | Fastest safe test | Authority |
|---|---|---|---|
| ETH Tier-1 cap envelope | upside High; evidence Low-Medium; realism Low now; costs modeled favorable; time Medium; account risk None now/Medium if cap changes; governance Medium; autonomy High | Let autonomous proposal carry `cost_gate_cap_envelope_evidence_floor_v1`; later review only if all floor evidence is present. | Research/proposal only; future cap envelope needs operator/QC/E3/BB before order. |
| AVAX scoped authorization admission | upside High path-enabler; evidence Medium-High; realism blocked by auth; cost favorable modeled; time Fast if valid auth appears; account risk None now; governance Medium; autonomy High | Review only a real AVAX-scoped typed-confirm/standing-auth artifact delta. | Candidate-scoped auth plus E3/BB; no authority now. |
| Current-cap low-price false-negative evidence floor | upside Medium; evidence Medium; realism Medium; cost Mixed; time Fast; account risk None source-only; governance Low; autonomy High | Source-only filter for sample size, spread, markout controls, and proof-exclusion lineage. | Research only; bounded auth before any order. |

## §5 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--cap_envelope_evidence_floor_source_patch.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T071429Z_cap_envelope_evidence_floor_source_only.json | sed -n '1,220p'
PYTHONPATH=helper_scripts/research python3 -m pytest -q /Users/ncyu/Projects/TradeBot/srv/helper_scripts/research/tests/test_cost_gate_autonomous_parameter_proposal.py /Users/ncyu/Projects/TradeBot/srv/helper_scripts/research/tests/test_cost_gate_false_negative_bounded_probe_preflight.py
ssh trade-core 'python3 -m json.tool /tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json | sed -n "1,120p"'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
**Self-check**: A next PM can identify the next action in under one minute: P0 auth is still blocked/no-repeat; v559 source patch is done/tested; runtime sync is a separate reviewed blocker if needed.
