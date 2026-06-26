# Xuanheng TODO - Active Dispatch Queue

**Version** v539 | **Date** 2026-06-26
**Source / runtime pointer**: Mac/origin `main` was clean at `7c5c36c7624b1911a0a1709c0b3a0f9f1c97e02d` before this source checkpoint. Linux runtime `trade-core` remains clean at `d2cd70d092916194043e112eeb402fb92bacb699`; no runtime source sync, service restart, rebuild, crontab/env mutation, PG write, Rust writer, adapter enablement, Bybit order/cancel/modify, Cost Gate change, or live action was performed.
**Current posture**: `P1-RUNTIME-HEALTH-HYGIENE-LOCAL-LINEAGE-68-STALE-WORKING` is `DONE_WITH_CONCERNS` as a source-only patch. Passive health [68] now distinguishes narrow close/risk local `Working` lineage residuals from real entry resting exposure, but the patch is not synced to Linux runtime. `P0-BOUNDED-PROBE-AUTHORIZATION` actual grant remains blocked on machine-checkable structured standing Demo authorization or exact typed confirm.
**Links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--health68_local_lineage_residual_source_patch.md`; prior auth report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--avax_authorization_review_ready_no_authority.md`; TODO standard `docs/agents/todo-maintenance.md`; changelog `docs/CLAUDE_CHANGELOG.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source | TODO v538 and this checkpoint: Linux repo clean at `d2cd70d0`; current Mac/origin head before this patch is `7c5c36c7`. | No runtime mutation occurred in v539; runtime will not see the [68] source fix until a separate source-sync/review checkpoint. |
| Selected candidate | v537 selected exactly one review-only candidate: `grid_trading|AVAXUSDT|Sell`, 60m, avg modeled net `73.5511bps`, `48/48` net-positive, cap `10 USDT`, min notional `5 USDT`. | Candidate selection is closed. Do not reselect without new candidate/cap/fee/touchability evidence. |
| Bounded authorization | v538 defer packet for AVAX is `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, no auth object, no active runtime probe/order authority, no Cost Gate adjustment. | Actual grant remains blocked by structured standing Demo authorization or exact typed confirm plus fresh E3/BB order-envelope/runtime review. |
| Learning SSOT / proposal | Prior reports `2026-06-24--learning_ssot_decision_packet.md` and `2026-06-24--autonomous_parameter_proposal_contract.md` already closed P1 source-only governance. | `P1-LEARNING-LOOP-CLOSURE` and `P1-AUTONOMOUS-PARAMETER-PROPOSAL` are `NO-OP_ALREADY_DONE`; do not rerun without new source/runtime/PG/artifact delta. |
| Health [68] source fix | v539 source patch: close/risk Working rows (`oc_risk_`, `oc_close_`, `oc_ipc_close_`, `risk_close:`, `strategy_close:`) with no same-symbol local filled position are visible `local_lineage_residual`, not entry exposure; normal entry Working rows and close/risk rows with a filled position still count. | This addresses the exchange-clean but local-stale `[68]` false-red shape without hiding real entry overhang. |
| PG / proof exclusions | v537 read-only PG: 72h demo fills `106`; missing order/context/blank strategy `0/0/0`; proof-excluded rows include `flash_dip_buy`, risk-close cleanup, and `unattributed:bybit_auto`. | These rows cannot count toward bounded-probe proof, Cost Gate proof, promotion evidence, or risk-adjusted net-PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T_p1_health68_local_lineage.json` |
| `active_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-LOCAL-LINEAGE-68-STALE-WORKING` |
| `blocker_goal` | Make passive health [68] distinguish exchange-clean local close/risk stale `Working` lineage residuals from real resting entry exposure, without hiding true open orders. |
| `profit_relevance` | Reducing false health blockers lets bounded Demo candidate review advance faster while preserving survival, auditability, and exchange/risk gates. |
| `previous_evidence_checked` | v538 auth checkpoint; v537 candidate packet; v536 cleanup report with post-action exchange clean and [68] false-red from four local close/risk `Working` rows; 2026-06-24 P1 learning/proposal reports. |
| `new_evidence_delta_required` | Exchange-clean post-action inventory plus [68] local-stale failure shape; no repeat of completed P1 learning/proposal source blockers. |
| `new_evidence_delta_found` | Post-clean exchange truth is open orders `0`, positions `0`, but [68] still saw demo `working_n=4`, `resting=398`, `filled=0`; source previously treated all latest `Working` rows as exposure. |
| `anti_repeat_decision` | `P1-LEARNING-LOOP-CLOSURE` -> `NO-OP_ALREADY_DONE`; `P1-AUTONOMOUS-PARAMETER-PROPOSAL` -> `NO-OP_ALREADY_DONE`; `[68]` hygiene -> `PROCEED_SOURCE_ONLY_NEW_EVIDENCE_DELTA`. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-68-RUNTIME-SYNC-REVIEW` |
| `why_not_repeating_current_blocker` | Source patch and focused review/tests are complete. Repeating local [68] source work without runtime sync/recheck or new [68] evidence adds no signal. |

## §2 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE_WITH_CONCERNS | PM -> QC/MIT/BB -> PM | Exactly one candidate selected; review-only packet; no probe/order/live authority; proof exclusions recorded. | Report `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading|AVAXUSDT|Sell`. | No-repeat unless new candidate/cap/fee/touchability evidence appears. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | PM -> E3 -> BB -> Operator/QC -> PM | Candidate-specific bounded Demo authorization packet only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless exact bounded authorization is admitted and later reviewed by E3/BB. | Report `2026-06-26--avax_authorization_review_ready_no_authority.md`; defer packet review-ready, no auth object, typed confirm missing. | To grant: admit valid `standing_demo_operator_authorization_v1` or exact typed confirm for `grid_trading|AVAXUSDT|Sell`, max `1`, TTL `<=4h`; then fresh E3/BB order-envelope/runtime-source/reconciliation review before any order. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Wait for an authorized bounded Demo probe with candidate-matched outcomes. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | DONE / NO-OP_ALREADY_DONE | PM -> PA/CC -> PM | Decide durable learning SSOT: artifact ledger vs PG-backed Cost Gate learning ledger. | Report `2026-06-24--learning_ssot_decision_packet.md`; current SSOT is artifact `probe_ledger.jsonl`; PG-backed cutover not ready. | Do not rerun unless learning SSOT source/runtime/PG/artifact evidence changes. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | DONE / NO-OP_ALREADY_DONE | PM -> PA/E1 -> E2 -> E4 -> PM | Learning output becomes reviewable proposal only; no direct order/risk/live mutation. | Report `2026-06-24--autonomous_parameter_proposal_contract.md`; proposals are inactive review packets with mutation false. | Do not rerun unless proposal contract source/runtime/artifact evidence changes. |
| `P1-RUNTIME-HEALTH-HYGIENE-LOCAL-LINEAGE-68-STALE-WORKING` | 1 | DONE_WITH_CONCERNS | PM -> E2 -> E4 -> PM | [68] keeps normal entry exposure fail-closed, but classifies close/risk no-position stale Working rows as visible local lineage residuals. | Report `2026-06-26--health68_local_lineage_residual_source_patch.md`; tests `30 passed`; E2 no blocker; E4 concern fixed with extra prefix tests. | No-repeat locally. Runtime still needs separate source-sync/recheck review. |
| `P1-RUNTIME-HEALTH-HYGIENE-68-RUNTIME-SYNC-REVIEW` | 1 | WAITING | PM -> E3 -> PM | Decide whether to sync the [68] source fix to Linux without restart, and define read-only post-sync/passive-health verification. | Current patch exists only on Mac/origin after commit; Linux runtime remains `d2cd70d0`. | Open a separate runtime/source-sync review before any Linux checkout change. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | WAITING | PM -> E3 -> BB -> PM | Reconcile runtime drift without unreviewed restart/rebuild/env mutation. | Linux checkout still `d2cd70d0`; no v539 sync/restart. | Consider after [68] sync review or if bounded authorization/admission requires runtime propagation. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | DEFERRED | PM -> BB/E2/E4 -> PM | Production full-scan pagination adoption path recorded and reviewed. | Mac source has full-scan helper; runtime source may still lack it depending on sync point. | Carry into runtime source-sync review only if future exchange inventory/reconciler work needs it. |

## §3 Hard Gates

| Gate | Trigger | Rule |
|---|---|---|
| Runtime source sync | Any Linux checkout/source update for [68] or bounded probe helpers. | Requires separate PM -> E3 review; no restart by default; no env/crontab mutation unless separately reviewed. |
| Authorization object | Any move from defer/review packet to granted bounded Demo probe. | Requires exact typed confirm or valid structured standing Demo authorization scoped to `grid_trading|AVAXUSDT|Sell`, max `1`, TTL `<=4h`, demo only. |
| Runtime/order path | Any public/private Bybit call, adapter/writer enablement, plan mutation, or order submission. | Requires fresh PM -> E3 -> BB -> PM order-envelope/runtime-source/reconciliation review. No current authority exists. |
| Cost Gate | Any attempt to reduce global Cost Gate or treat a row as proof. | Global Cost Gate must not be lowered. Proof must be candidate-matched and include fills, fees, slippage, lineage, controls, and execution realism. |
| Live/mainnet | Any mainnet key/order/path. | Out of scope; no live authority. |

## §4 Safety Invariants And Proof Exclusions

- Profit is optimized only inside survival, Guardian/risk gates, Decision Lease, Rust authority, authorization gates, auditability, and reconstructability.
- Do not lower global Cost Gate, widen caps/freshness gates, fake freshness, or bypass Guardian/risk/Decision Lease/Rust authority.
- `flash_dip_buy` demo fills, cleanup/risk-close fills, unattributed fills, local stale Working rows, artifact counts, source-smoke, single-window MM positives, and replay-only results cannot count as Cost Gate, bounded-probe, promotion, or risk-adjusted net-PnL proof.
- Learning output may become a reviewable proposal only; it must not directly mutate order/risk/live state.

## §5 Aggressive Alpha Backlog

| Hypothesis | Score snapshot | Why it might make money | Fastest safe test | Required data | Failure condition | Authority |
|---|---|---|---|---|---|---|
| AVAX false-negative near-touch bounded Demo | upside High; evidence Medium; realism Medium; cost Good; time Fast; account risk Low if capped; governance risk Medium; autonomy High | Historic blocked outcomes clear current modeled cost by wide margin; near-touch-or-skip may convert false-negative edge into real candidate-matched fills. | Exact no-authority authorization packet first; after valid grant, one capped Demo post-only near-touch-or-skip attempt with fresh BBO and full lineage. | Valid authorization object, fresh BBO, cap/min-notional, order/fill/fee/slippage lineage, matched blocked controls. | No touch, taker fill, stale BBO, missing lineage, net after fees/slippage <= 0, or control underperforms. | Structured bounded Demo authorization + E3/BB order-envelope review required. |
| [68] false-blocker reduction | upside Medium; evidence High; realism High; cost Neutral; time Fast; account risk Low; governance Low-Medium; autonomy Medium | Removing local lineage false-reds lets safe candidate review proceed without weakening exchange truth or hiding entry exposure. | Source-sync review plus read-only passive health recheck after sync. | Runtime source head, passive health [68] output, exchange-clean inventory or no-new-exposure evidence. | Any normal entry Working row is hidden, or exchange inventory shows open exposure. | Runtime source-sync review required; no restart/order. |
| Current-fee maker/MM repeat-window branch | upside Medium; evidence Low; realism Low-Medium; cost Tight; time Medium; account risk None source-only; governance Low | Repeated maker-positive windows could become a low-cost execution path without lowering Cost Gate. | Accumulate independent windows and maker-realism score without claiming proof. | Recent maker/taker fees, fills, queue proxies, spread/markout, distinct dates. | Single-window only, net cushion below fees/slippage, or maker ratio cannot be achieved. | Research/proposal only. |

## §6 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--health68_local_lineage_residual_source_patch.md
python3 -m pytest -q /Users/ncyu/Projects/TradeBot/srv/helper_scripts/db/test_portfolio_resting_exposure_healthcheck.py /Users/ncyu/Projects/TradeBot/srv/helper_scripts/db/test_wp03_deploy_gate_healthcheck.py
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T_p1_health68_local_lineage.json | sed -n '1,220p'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
