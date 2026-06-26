# Xuanheng TODO - Active Dispatch Queue

**Version** v561 | **Date** 2026-06-26
**Source/runtime pointer**: repo `main` / `origin/main` at `0685908f87dd6c91c28f8acbc0c2d1e1a1d79bb2`; Linux runtime source and crontab expected-head pins at `dd22810ee41c353c1d214d9a3217862d7b2bac74`.
**Current posture**: TODO compliance compaction done; operator requested pause after this round. P0 authorization remains blocked/no-repeat unless a real candidate-scoped auth delta appears.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--todo_maintenance_compliance_compaction.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source/services | `2026-06-26T07:35:35Z`: Linux runtime source clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74`; API service `active`, MainPID `2218842`. | Runtime sync blocker is closed. Do not repeat sync unless source/crontab drift is observed. |
| Artifact SSOT path | Current cost-gate artifacts are under `/tmp/openclaw/cost_gate_learning_lane/`. | Read-only checks must use this subdirectory. |
| Autonomous proposal latest | `2026-06-26T07:29:20Z`, sha `a71a5b06...`, `REVIEWABLE_PARAMETER_PROPOSAL_READY`, candidate `grid_trading\|AVAXUSDT\|Sell`, contains `cost_gate_cap_envelope_evidence_floor_v1`, `cap_envelope_mutation_allowed=false`. | Natural artifact refresh confirmed the v559 evidence-floor contract is active. This is proposal/review evidence only, not cap/order authority. |
| Authorization latest | `2026-06-26T07:30:55Z`, sha `90322ebc...`, status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, candidate `grid_trading\|AVAXUSDT\|Sell`, decision defer/no authority. | This is a fresh artifact delta but not an authorization delta. P0 bounded probe authorization stays blocked/no-repeat. |
| AVAX bounded candidate | Selected bounded Demo candidate remains `grid_trading\|AVAXUSDT\|Sell`, 60m, current-cap feasible, modeled `73.5511bps`, `48/48` positive. | Candidate selection is closed. Do not replace AVAX without fresh ranking/cap-feasibility evidence. |
| ETH cap staircase | ETH Buy remains high-upside research-only; current `10 USDT` cap cannot construct it. At recorded `1571.05` price and `0.01 ETH` step: `15.7105`, `31.4210`, `47.1315 USDT`. | Any ETH cap envelope needs a separate operator/QC/E3/BB review; no cap mutation now. |
| Proof exclusions | Exclude `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale `Working` rows, artifact counts, source-smoke, single-window MM positives, and replay-only results. | These never count for bounded-probe proof, Cost Gate proof, promotion, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T073551Z_todo_maintenance_compliance_compaction.json` |
| `active_blocker_id` | `P1-TODO-MAINTENANCE-COMPLIANCE-COMPACTION` |
| `blocker_goal` | Bring `TODO.md` back to the active-queue standard: compact masthead, timestamped current facts, explicit gates, no long report bodies, no passive next action. |
| `profit_relevance` | Reduces repeated no-delta audits and stale dispatch, letting the loop spend time on real alpha/profit checkpoints instead of bookkeeping drift. |
| `previous_evidence_checked` | `docs/agents/todo-maintenance.md`; TODO v560; runtime source/service snapshot; natural cost-gate latest artifacts. |
| `new_evidence_delta_required` | Source-only TODO compliance gap plus any natural artifact delta needed to avoid stale current facts. |
| `new_evidence_delta_found` | TODO had stale auth latest and a passive natural-refresh next action; runtime artifacts naturally refreshed with cap floor present and auth still defer/no-authority. |
| `anti_repeat_decision` | Do not rerun P0 auth or runtime sync. This round is source/doc-only TODO maintenance requested by operator. |
| `loop_status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P1-AGGRESSIVE-ALPHA-LOW-PRICE-FALSE-NEGATIVE-EVIDENCE-FLOOR-RANKING-NO-ORDER` after operator resumes. |
| `why_not_repeating_current_blocker` | TODO is now compact and timestamped; repeating this without a new TODO drift or stale fact would be anti-repeat noise. |

## §2 Active Dispatch Queue

| ID | P | Status | Loop decision | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> E3/BB/QC -> PM | Demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; §0 proof exclusions. | No-repeat unless exchange inventory, fill attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority. | `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading\|AVAXUSDT\|Sell`. | No-repeat unless fresh evidence invalidates AVAX cap feasibility or ranking. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | `BLOCKED_BY_RUNTIME_AUTHORIZATION` | PM -> E3 -> BB -> PM | Candidate-specific bounded Demo auth only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless valid scoped authorization is admitted and E3/BB review passes. | `2026-06-26T07:30:55Z` auth latest sha `90322ebc...`: AVAX-scoped, `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, defer/no authority. | No read-only repeat. Resume only on candidate-scoped typed-confirm, standing-auth, or authority artifact delta. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | `WAITING_FOR_AUTHORIZED_OUTCOMES` | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe has candidate-matched outcomes. |
| `P1-AUTHORIZATION-GATE-STATUS-CLARITY-SOURCE-FIX` | 1 | DONE | `DONE_WITH_CONCERNS` | PM-local PA/E1/E2/E4/QA equivalent | False-negative preflight/operator-review blocker labels are accurate and fail closed. | Commit `99d3b8f7`; focused suites passed. | No-repeat unless auth schema/status contracts change. |
| `P1-RUNTIME-HEALTH-HYGIENE-AUTH-STATUS-CLARITY-SYNC-REVIEW` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> E3 -> PM | Runtime source/pins aligned to v556 without service restart/manual cron/order/authority. | `2026-06-26--authorization_gate_status_clarity_runtime_sync.md`. | No-repeat unless runtime source/crontab drifts again. |
| `P1-AGGRESSIVE-ALPHA-ETH-CAP-ENVELOPE-SENSITIVITY-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> QC/MIT-equivalent -> PM | ETH cap tiers quantified; no cap mutation; no proof/authority claim. | `2026-06-26--eth_cap_envelope_sensitivity_no_order.md`. | No-repeat unless ETH price/metadata/cap/evidence changes. |
| `P1-AGGRESSIVE-ALPHA-CAP-ENVELOPE-EVIDENCE-FLOOR-SOURCE-ONLY` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Autonomous proposal emits cap-envelope evidence floor; no cap mutation or authority. | Commit `dd22810e`; focused tests `10 passed`; natural latest now has cap floor. | No-repeat unless source contract requirements change. |
| `P1-RUNTIME-HEALTH-HYGIENE-CAP-ENVELOPE-PROPOSAL-SYNC-REVIEW` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> E3 -> PM | Runtime source/crontab expected-head pins aligned to v559 without service restart/manual cron/PG/Bybit/order/authority. | `2026-06-26--cap_envelope_proposal_runtime_sync.md`; runtime head `dd22810e`; API PID unchanged. | No-repeat unless runtime source/crontab drifts again. |
| `P1-TODO-MAINTENANCE-COMPLIANCE-COMPACTION` | 1 | DONE | `DONE_WITH_CONCERNS` | PM | TODO follows active-queue standard and records fresh natural artifact facts without creating authority/proof claims. | `2026-06-26--todo_maintenance_compliance_compaction.md`; this v561 file. | No-repeat unless TODO drifts from `docs/agents/todo-maintenance.md`. |
| `P1-AGGRESSIVE-ALPHA-LOW-PRICE-FALSE-NEGATIVE-EVIDENCE-FLOOR-RANKING-NO-ORDER` | 1 | DEFERRED | `READY_AFTER_OPERATOR_RESUME` | PM -> QC/MIT -> PM | Rank current-cap false-negative candidates against the evidence-floor dimensions; no order, no cap mutation, no authority. | Natural scorecard latest `2026-06-26T07:30:55Z`, sha `7361c1dc...`. | After pause/resume, run source-only ranking; do not wait/observe as the next action. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Survival/risk | Profit is optimized only inside survival, Guardian/risk, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| Authorization | Demo API permission is not live/mainnet permission. Bounded Demo grant requires candidate-scoped structured auth or exact typed confirm plus E3/BB review. |
| Runtime/order path | Bybit private/trading calls, adapter/writer enablement, plan mutation, order submission, PG write, crontab/env edit, or service restart require reviewed runtime chain. |
| Cost Gate | Global Cost Gate must not be lowered. Proof must be candidate-matched and include fills, fees, slippage, lineage, controls, and execution realism. |
| Candidate selection | AVAX remains the P0 bounded candidate. ETH is research-only until separate cap-envelope review. |
| Live/mainnet | Out of scope; no live/mainnet authority. |

## §4 Aggressive Alpha Backlog

| Hypothesis | Score snapshot | Fastest safe test | Authority |
|---|---|---|---|
| Current-cap low-price false-negative evidence floor | upside Medium; evidence Medium; realism Medium; cost Mixed; time Fast; account risk None source-only; governance Low; autonomy High | Source-only ranking using cap feasibility, sample size, spread/markout controls, and proof-exclusion lineage. | Research only; bounded auth before any order. |
| ETH Tier-1 cap envelope | upside High; evidence Low-Medium; realism Low now; costs modeled favorable; time Medium; account risk None now/Medium if cap changes; governance Medium; autonomy High | Review only if autonomous proposal floor evidence is complete and cap-envelope math survives QC/E3/BB. | Research/proposal only; future cap envelope needs operator/QC/E3/BB before order. |
| AVAX scoped authorization admission | upside High path-enabler; evidence Medium-High; realism blocked by auth; cost favorable modeled; time Fast if valid auth appears; account risk None now; governance Medium; autonomy High | Review only a real AVAX-scoped typed-confirm/standing-auth artifact delta. | Candidate-scoped auth plus E3/BB; no authority now. |

## §5 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--todo_maintenance_compliance_compaction.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T073551Z_todo_maintenance_compliance_compaction.json | sed -n '1,220p'
ssh trade-core 'python3 -m json.tool /tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json | sed -n "1,120p"'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: A next PM can identify the next action in under one minute: pause now; after resume, run source-only low-price false-negative evidence-floor ranking unless a real P0 auth delta appears first.
