# Xuanheng TODO - Active Dispatch Queue

**Version** v563 | **Date** 2026-06-26
**Source/runtime pointer**: v563 source-code checkpoint commit `b79a3c2fdd7cd8792af550d2114858e0362c049f` is on `main` / `origin/main`; this TODO lives at current repo HEAD. Linux runtime source and crontab expected-head pins remain `dd22810ee41c353c1d214d9a3217862d7b2bac74`.
**Current posture**: evidence-floor gap-closure design is `DONE_WITH_CONCERNS`; operator requested pause after this round. P0 authorization remains blocked/no-repeat unless a real candidate-scoped auth delta appears.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--evidence_floor_gap_closure_design_no_order.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source/services | `2026-06-26T07:56:56Z`: Linux runtime source clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74`; API service `active`, MainPID `2218842`. | Runtime is intentionally not changed by v563. Do not sync/restart unless a separate runtime blocker is opened. |
| Artifact SSOT path | Current cost-gate artifacts are under `/tmp/openclaw/cost_gate_learning_lane/`. | Read-only checks must use this subdirectory. |
| Authorization latest | `2026-06-26T07:45:05Z`, sha `0704af04...`, status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, candidate `grid_trading\|AVAXUSDT\|Sell`, decision defer/no authority. | Fresh artifact delta exists but it is not an authorization delta. P0 bounded probe authorization stays blocked/no-repeat. |
| Autonomous proposal latest | `2026-06-26T07:29:20Z`, sha `a71a5b06...`, `REVIEWABLE_PARAMETER_PROPOSAL_READY`, candidate `grid_trading\|AVAXUSDT\|Sell`, has `cost_gate_cap_envelope_evidence_floor_v1`, `cap_envelope_mutation_allowed=false`. | Proposal/review evidence only; no cap/order authority. |
| Evidence-floor ranking smoke | `/tmp/openclaw/false_negative_evidence_floor_ranking_smoke_20260626T074233Z/ranking.json`: `FALSE_NEGATIVE_EVIDENCE_FLOOR_RANKING_READY_NO_AUTHORITY`, leader `grid_trading\|AVAXUSDT\|Sell`, `REVIEW_ONLY_LEADER_NOT_PROOF`, `floor_satisfied_count=0`. | Ranking is closed; do not rerun on same artifacts. |
| Evidence-floor gap-closure smoke | `/tmp/openclaw/false_negative_evidence_floor_gap_closure_smoke_20260626T075631Z/gap_closure.json`: `EVIDENCE_FLOOR_GAP_CLOSURE_DESIGN_READY_NO_AUTHORITY`, candidate `grid_trading\|AVAXUSDT\|Sell`, `gap_count=9`, authority/proof false. | Gap design is closed; next source-only work should implement a specific contract, not another audit. |
| AVAX bounded candidate | Selected bounded Demo candidate remains `grid_trading\|AVAXUSDT\|Sell`, 60m, current-cap feasible, modeled `73.5511bps`, `48/48` positive. | Candidate selection is closed. Do not replace AVAX without fresh ranking/cap-feasibility evidence. |
| Proof exclusions | Exclude `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale `Working` rows, artifact counts, source-smoke, single-window MM positives, and replay-only results. | These never count for bounded-probe proof, Cost Gate proof, promotion, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T075631Z_evidence_floor_gap_closure_design_no_order.json` |
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-EVIDENCE-FLOOR-GAP-CLOSURE-DESIGN-NO-ORDER` |
| `blocker_goal` | Define the smallest no-order, source-only evidence closure path for the AVAX evidence-floor leader without changing cap/risk/runtime/order state or granting authority. |
| `profit_relevance` | Turns the AVAX review-only leader into explicit evidence gates required before any real risk-adjusted net PnL proof after fees/slippage can be claimed. |
| `previous_evidence_checked` | v562 TODO; ranking report; latest scorecard/proposal/auth artifact mtimes; ranking smoke. |
| `new_evidence_delta_required` | Completed ranking with `floor_satisfied_count=0` and AVAX review-only leader; no real P0 auth delta. |
| `new_evidence_delta_found` | Gap-closure smoke maps nine AVAX evidence-floor gaps into source-only/read-only-runtime/future-authorization lanes. |
| `anti_repeat_decision` | Proceeded with a distinct source-only helper; do not rerun ranking/gap audit on the same artifacts. |
| `loop_status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `PAUSED_AFTER_V563_OPERATOR_REQUEST`; on resume use P0 auth delta if real, otherwise `P1-AGGRESSIVE-ALPHA-SOURCE-ONLY-CONTROL-IDENTITY-CONTRACT-NO-ORDER`. |
| `why_not_repeating_current_blocker` | Gap closure is source-backed and smoke-tested; repeating would add no evidence. |

## §2 Active Dispatch Queue

| ID | P | Status | Loop decision | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> E3/BB/QC -> PM | Demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; §0 proof exclusions. | No-repeat unless exchange inventory, fill attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority. | `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading\|AVAXUSDT\|Sell`. | No-repeat unless fresh evidence invalidates AVAX cap feasibility or ranking. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | `BLOCKED_BY_RUNTIME_AUTHORIZATION` | PM -> E3 -> BB -> PM | Candidate-specific bounded Demo auth only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless valid scoped authorization is admitted and E3/BB review passes. | `2026-06-26T07:45:05Z` auth latest sha `0704af04...`: AVAX-scoped, `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, defer/no authority. | No read-only repeat. Resume only on candidate-scoped typed-confirm, standing-auth, or authority artifact delta. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | `WAITING_FOR_AUTHORIZED_OUTCOMES` | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe has candidate-matched outcomes. |
| `P1-AGGRESSIVE-ALPHA-LOW-PRICE-FALSE-NEGATIVE-EVIDENCE-FLOOR-RANKING-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Machine-checkable source-only ranking helper exists; AVAX leader remains review-only; no candidate has floor-satisfied proof. | `2026-06-26--low_price_false_negative_evidence_floor_ranking_no_order.md`; smoke `floor_satisfied_count=0`. | No-repeat unless scorecard/cap/proposal/auth artifacts change. |
| `P1-AGGRESSIVE-ALPHA-EVIDENCE-FLOOR-GAP-CLOSURE-DESIGN-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Source-only gap-closure helper exists; AVAX gaps are lane-separated; no proof/authority/cap/runtime mutation. | `2026-06-26--evidence_floor_gap_closure_design_no_order.md`; smoke `gap_count=9`, authority false. | No-repeat on same ranking/auth artifacts. |
| `P1-AGGRESSIVE-ALPHA-SOURCE-ONLY-CONTROL-IDENTITY-CONTRACT-NO-ORDER` | 1 | WAITING | `WAITING_OPERATOR_RESUME` | PM -> QC/MIT -> PM | Define exact candidate/control identity contract for future AVAX proof: side-cell keys, blocked-control match keys, exclusion rules, result-review join requirements, and no-authority answers. | Gap-closure helper says first source-only lane is `candidate_matched_controls_present`. | After operator resumes and if no real P0 auth delta exists, implement this specific source-only contract. |

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
| AVAX source-only control identity contract | upside Medium-High; evidence Medium; realism Low until fills; cost modeled favorable; time Fast; account risk None; governance Low; autonomy High | Source-only contract for candidate identity, control matching keys, proof exclusions, and future result-review joins. | None for contract; candidate-scoped bounded auth plus PM->E3->BB before any order. |
| AVAX current-cap staircase + risk worksheet | upside Medium; evidence Medium-Low; realism Low; cost modeled favorable; time Fast; account risk None now; governance Low-Medium; autonomy Medium | Source-only/current-cap worksheet plus reviewed read-only instrument metadata path. | None for worksheet; operator/QC/E3/BB for any cap/risk mutation. |
| Regime/OOS labels for false-negative subset | upside Medium; evidence Low-Medium; realism Medium source-only; cost unknown; time Medium; account risk None; governance Low; autonomy High | Source-only leak-free label/join contract before any PG/runtime query. | None for design; reviewed read-only path if runtime/PG labels are queried later. |

## §5 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--evidence_floor_gap_closure_design_no_order.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T075631Z_evidence_floor_gap_closure_design_no_order.json | sed -n '1,220p'
python3 -m json.tool /tmp/openclaw/false_negative_evidence_floor_gap_closure_smoke_20260626T075631Z/gap_closure.json | sed -n '1,180p'
ssh trade-core 'python3 -m json.tool /tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json | sed -n "1,120p"'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: A next PM can identify the next action in under one minute: stop now per operator request; on resume, real P0 auth delta takes precedence, otherwise implement the source-only control identity contract.
