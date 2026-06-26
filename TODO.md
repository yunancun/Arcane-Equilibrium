# Xuanheng TODO - Active Dispatch Queue

**Version** v545 | **Date** 2026-06-26
**Repo/runtime pointer**: Mac/origin `main` was clean at docs checkpoint `90b9f44b5ca7fda64daaac0f27cb496a7c327bc2` before this docs checkpoint. Linux runtime `trade-core` remains source-clean at runtime code checkpoint `0246b26361e403e6cb1ddd126eba8e3cd7b91a23`.
**Current posture**: `P0-BOUNDED-PROBE-AUTHORIZATION` is `BLOCKED_BY_RUNTIME_AUTHORIZATION` with no new AVAX-scoped authorization delta; repeated no-authority audit is `NO-OP_NO_EVIDENCE_DELTA`. Next executable blocker after the requested pause is source-only `P1-AGGRESSIVE-ALPHA-FALSE-NEGATIVE-SUBSET-MINING-NO-ORDER`.
**Links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--bounded_probe_authorization_antirepeat_todo_hygiene.md`; version changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime hygiene | `2026-06-26T04:34:19Z` post-alignment packet is `RUNTIME_HEALTH_HYGIENE_CLEAN_SOURCE_ONLY`; source/crontab/API/artifact compatibility clean; all mutation/authority/proof answers false/NONE. | Hygiene false blockers are closed. This is not profit/probe proof and grants no authority. |
| Runtime source/services | Linux runtime source is clean at `0246b26361e403e6cb1ddd126eba8e3cd7b91a23`; crontab expected-head pins match; user API/watchdog services are active/enabled per latest hygiene report. | Do not repeat [68], runtime sync, crontab alignment, or hygiene snapshot without new source/crontab/service/artifact delta. |
| Learning artifacts | `mm_current_fee_confirmation_latest` is `NO_CURRENT_FEE_POSITIVE_MM_CELL`; `false_negative_candidate_friction_scorecard_latest` is `FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY`. | MM current-fee is not the fastest positive branch now. False-negative source-only mining is the next useful alpha path. |
| Selected candidate | `grid_trading|AVAXUSDT|Sell`, 60m, avg modeled net `73.5511bps`, `48/48` net-positive, cap `10 USDT`, min notional `5 USDT`. | Candidate selection is closed. Do not reselect without new candidate/cap/fee/touchability evidence. |
| Bounded authorization | Runtime latest auth artifact checked this round: `decision=defer`, `candidate=grid_trading|ETHUSDT|Buy`, `authorization_id=null`, no standing auth, no emitted object, no runtime probe/order authority. | No AVAX-scoped authorization delta. Stop before orders; move only to source-only work unless valid AVAX authorization appears. |
| Proof exclusions | `flash_dip_buy`, cleanup/risk-close, unattributed fills, local stale rows, artifact counts, source-smoke, single-window MM positives, replay-only results. | Never count these as bounded-probe proof, Cost Gate proof, promotion evidence, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T044212Z_bounded_probe_authorization_antirepeat.json` |
| `active_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION` |
| `blocker_goal` | Determine whether selected `grid_trading|AVAXUSDT|Sell` can advance from no-authority review to bounded Demo authorization without repeating prior no-authority audits. |
| `profit_relevance` | A valid bounded Demo authorization is the fastest safe path to candidate-matched net-PnL execution evidence, but broad intent cannot become order/probe authority. |
| `previous_evidence_checked` | Reports `2026-06-26--avax_authorization_review_ready_no_authority.md`, `2026-06-24--bounded_probe_authorization_exact_confirm_gate.md`, `2026-06-26--runtime_health_hygiene_post_alignment_snapshot.md`; runtime latest auth artifact. |
| `new_evidence_delta_required` | Valid `standing_demo_operator_authorization_v1` or exact typed confirm scoped to `grid_trading|AVAXUSDT|Sell`, max `1`, TTL `<=4h`, Demo/LiveDemo only, then fresh PM -> E3 -> BB review. |
| `new_evidence_delta_found` | None. Runtime latest is defer-only, candidate-mismatched to `ETHUSDT|Buy`, and has no authorization object or runtime authority. |
| `anti_repeat_decision` | `BLOCKED_BY_RUNTIME_AUTHORIZATION` for actual grant; repeated no-authority audit is `NO-OP_NO_EVIDENCE_DELTA`. |
| `status` | `BLOCKED_BY_RUNTIME_AUTHORIZATION` |
| `next_blocker_id` | `P1-AGGRESSIVE-ALPHA-FALSE-NEGATIVE-SUBSET-MINING-NO-ORDER` |
| `why_not_repeating_current_blocker` | Same blocker already has previous reports and no new AVAX-scoped source/runtime/PG/artifact/operator authorization delta. |

## §2 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE_WITH_CONCERNS | PM -> E3/BB/QC -> PM | Demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; proof exclusions carried in §0/§4. | No-repeat unless new exchange inventory, fills attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE_WITH_CONCERNS | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority. | `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading|AVAXUSDT|Sell`. | No-repeat unless new candidate/cap/fee/touchability evidence appears. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED_BY_RUNTIME_AUTHORIZATION | PM -> E3 -> BB -> PM | Candidate-specific bounded Demo auth only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless valid authorization is admitted and E3/BB review passes. | `2026-06-26--bounded_probe_authorization_antirepeat_todo_hygiene.md`; runtime latest is defer-only and candidate-mismatched. | Do not rerun no-authority audit. Resume only if valid AVAX scoped auth appears; otherwise use next source-only blocker. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Wait condition: only after authorized bounded Demo probe with candidate-matched outcomes. |
| `P1-AGGRESSIVE-ALPHA-FALSE-NEGATIVE-SUBSET-MINING-NO-ORDER` | 1 | ACTIVE | PM -> QC -> MIT -> AI-E -> PM | Source-only proposal selecting high-cushion false-negative subclusters/filters; no orders, no authority, no Cost Gate lowering. | MM current-fee now `NO_CURRENT_FEE_POSITIVE_MM_CELL`; false-negative scorecard remains ready. | After this requested pause, mine latest scorecard for one review-only alpha expansion packet. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | DONE / NO-OP_ALREADY_DONE | PM -> PA/CC -> PM | Durable learning SSOT selected. | `2026-06-24--learning_ssot_decision_packet.md`; artifact `probe_ledger.jsonl` remains current SSOT. | No-repeat unless SSOT source/runtime/PG/artifact evidence changes. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | DONE / NO-OP_ALREADY_DONE | PM -> PA/E1 -> E2 -> E4 -> PM | Learning output becomes reviewable proposal only; no direct order/risk/live mutation. | `2026-06-24--autonomous_parameter_proposal_contract.md`. | No-repeat unless proposal contract evidence changes. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | DONE_WITH_CONCERNS / NO-OP_ALREADY_DONE | PM -> E3 -> PM | [68], runtime sync, crontab expected-head, and post-alignment hygiene closed without authority/proof contamination. | Latest `2026-06-26--runtime_health_hygiene_post_alignment_snapshot.md`; clean packet path in §0. | No-repeat unless source/crontab/user-service/artifact evidence changes. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | DEFERRED | PM -> BB/E2/E4 -> PM | Production full-scan pagination adoption path recorded and reviewed. | Mac source has helper; no exchange-facing use authorized here. | Carry into future exchange-inventory/reconciler blocker only if needed. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Authorization | Any move from defer/review to bounded Demo grant requires valid AVAX-scoped structured auth or exact typed confirm plus fresh E3/BB review. |
| Runtime/order path | Any Bybit call, adapter/writer enablement, plan mutation, or order submission requires PM -> E3 -> BB -> PM. No current authority exists. |
| Cost Gate | Global Cost Gate must not be lowered. Proof must be candidate-matched and include fills, fees, slippage, lineage, controls, and execution realism. |
| Live/mainnet | Out of scope; no live/mainnet authority. |
| Runtime mutation | Source sync, crontab/env edits, service restart/rebuild/daemon-reload, and PG writes require a separate reviewed blocker. |

## §4 Safety Invariants And Proof Exclusions

- Profit is optimized only inside survival, Guardian/risk gates, Decision Lease, Rust authority, authorization gates, auditability, and reconstructability.
- Learning output may become a reviewable proposal only; it must not directly mutate order/risk/live state.
- Exclude from proof: `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale Working rows, artifact counts, source-smoke, single-window MM positives, and replay-only results.

## §5 Aggressive Alpha Backlog

| Hypothesis | Score snapshot | Fastest safe test | Authority |
|---|---|---|---|
| False-negative subset mining under no-order mode | upside Medium-High; evidence Medium; realism Medium; cost Good; time Fast; account risk None; governance Low; autonomy High | Source-only scorecard slice by symbol/horizon/regime/placement feasibility; emit one review-only proposal. | Research/proposal only. |
| AVAX near-touch bounded Demo after valid auth | upside High; evidence Medium; realism Medium; cost Good; time Fast after auth; account risk Low if capped; governance Medium; autonomy High | After valid AVAX auth plus E3/BB: one capped post-only near-touch-or-skip attempt. | Structured bounded Demo authorization + E3/BB required. |
| Fee/friction reduction path | upside Medium; evidence Low-Medium; realism Medium; cost Potentially Good; time Medium; account risk None source-only; governance Low; autonomy Medium | Source-only fee/friction decomposition across blocked candidates and maker-feasible windows. | Research/proposal only. |

## §6 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--bounded_probe_authorization_antirepeat_todo_hygiene.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T044212Z_bounded_probe_authorization_antirepeat.json | sed -n '1,220p'
ssh trade-core 'jq "{decision, candidate: .candidate.side_cell_key, status, authorization_id, answers}" /tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
