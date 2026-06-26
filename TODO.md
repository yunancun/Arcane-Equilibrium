# Xuanheng TODO - Active Dispatch Queue

**Version** v543 | **Date** 2026-06-26
**Repo/runtime pointer**: Mac/origin `main` was clean at docs checkpoint `1678f00f3008ab21f7b3651df175176e4aa51667` before this docs checkpoint. Linux runtime `trade-core` is source-clean at runtime code checkpoint `0246b26361e403e6cb1ddd126eba8e3cd7b91a23`; crontab expected-head pins now match that runtime head.
**Current posture**: Current blocker `P1-RUNTIME-HEALTH-HYGIENE-CRON-EXPECTED-HEAD-DRIFT-REVIEW` is closed `DONE_WITH_CONCERNS`; per operator request, do not start the next blocker until resume. Active queue is in §2.
**Links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--cron_expected_head_drift_alignment.md`; version changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source | `2026-06-26T04:21:04Z` read-only check: Linux `/home/ncyu/BybitOpenClaw/srv` `HEAD=0246b26361e403e6cb1ddd126eba8e3cd7b91a23`, worktree status count `0`. | Runtime has the [68] local-lineage source fix. Docs/TODO-only commits above `0246b263` do not imply runtime sync. |
| Cron expected-head | E3-approved expected-head-only crontab alignment completed at audit dir `/tmp/openclaw/audit/crontab_expected_head_sync_20260626T041735Z`: line count `70`, old literal `d2cd70d0...` count `0`, new literal `0246b263...` count `11`, matching lines `57,67,68,69,70`. | Source-mismatch noise from stale cron pins is removed. This is not a profit/probe proof. |
| Runtime authority flags | Same crontab check: `OPENCLAW_ALLOW_MAINNET=1` count `0`, `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED` count `0`, `RECORD_PROBE_OUTCOMES=1` count `0`, `OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=0` count `1`. | No live/mainnet, adapter, probe-outcome recording, or Cost Gate authority was enabled. |
| API/watchdog services | Correct user-service scope at `2026-06-26T04:21:04Z`: `openclaw-trading-api.service` active/enabled, MainPID `2218842`; `openclaw-watchdog.service` active/running/enabled. System-level names `openclaw-api`/`openclaw-watchdog` are inactive and are not the canonical user-service checks. | Use `systemctl --user` checks for API/watchdog ownership. Do not create a false blocker from wrong systemd scope. |
| Selected candidate | Review-only candidate remains `grid_trading|AVAXUSDT|Sell`, 60m, avg modeled net `73.5511bps`, `48/48` net-positive, cap `10 USDT`, min notional `5 USDT`. | Candidate selection is closed. Do not reselect without new candidate/cap/fee/touchability evidence. |
| Bounded authorization | Latest AVAX packet is review-ready/defer-only with no authorization object, no active runtime probe/order authority, and no Cost Gate adjustment. Broad chat authorization is not a machine-checkable bounded-probe grant. | Actual bounded Demo execution remains blocked until a valid structured standing Demo authorization or exact typed confirm is admitted, then E3/BB order-envelope review passes. |
| Proof exclusions | `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale rows, artifact counts, source-smoke, single-window MM positives, and replay-only results remain proof-excluded. | These cannot count toward bounded-probe proof, Cost Gate proof, promotion evidence, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T041121Z_cron_expected_head_drift_review.json` |
| `active_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-CRON-EXPECTED-HEAD-DRIFT-REVIEW` |
| `blocker_goal` | Align stale crontab expected-head pins from `d2cd70d0` to verified runtime code checkpoint `0246b263` only if E3 allows, without schedule/flag/env/log/service/PG/Bybit/Cost Gate/authority mutation. |
| `profit_relevance` | Stale cron pins can make scheduled learning/health artifacts report source mismatch, slowing bounded Demo candidate review and autonomous learning feedback. |
| `previous_evidence_checked` | Reports `2026-06-26--health68_runtime_source_sync_review.md`, `2026-06-26--health68_local_lineage_residual_source_patch.md`, `2026-06-26--avax_authorization_review_ready_no_authority.md`, and prior cron precedent `2026-06-24--runtime_cron_expected_head_patch_api_ownership.md`. |
| `new_evidence_delta_required` | Post-[68]-sync runtime crontab still had stale expected-head `d2cd70d0` pins while runtime source was verified at `0246b263`. |
| `new_evidence_delta_found` | Baseline old literal count `11` on lines `57,67,68,69,70`; E3 allowed exact literal replacement only. Post-check old count `0`, new count `11`, line count `70`, forbidden authority flags unchanged, runtime source still clean at `0246b263`, user API service still MainPID `2218842`, user watchdog active/running. |
| `anti_repeat_decision` | Proceeded because this blocker had a real runtime evidence delta after the [68] sync. Did not repeat completed [68] source patch or runtime source sync. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-CRON-POST-ALIGNMENT-HYGIENE-SNAPSHOT` |
| `pause_state` | Paused after this round by operator request. Do not start the next blocker until resume. |
| `why_not_repeating_current_blocker` | Crontab expected-head alignment is complete and post-checked. Repeating the same crontab edit without new source/runtime/crontab evidence would violate anti-repeat. |

## §2 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE_WITH_CONCERNS | PM -> E3/BB/QC -> PM | Deep/open demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | Clean exchange-book report `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; proof exclusions carried in §0/§4. | No-repeat unless new exchange inventory, fills attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE_WITH_CONCERNS | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority; proof exclusions recorded. | Report `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading|AVAXUSDT|Sell`. | No-repeat unless new candidate/cap/fee/touchability evidence appears. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | PM -> E3 -> BB -> Operator/QC -> PM | Candidate-specific bounded Demo authorization only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless exact bounded authorization is admitted and E3/BB review passes. | Report `2026-06-26--avax_authorization_review_ready_no_authority.md`; no authorization object. | On resume, do not execute orders. First admit a machine-checkable `standing_demo_operator_authorization_v1` or exact typed confirm for `grid_trading|AVAXUSDT|Sell`, max `1`, TTL `<=4h`, then run fresh E3/BB order-envelope/runtime review. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Wait condition: only after an authorized bounded Demo probe with candidate-matched outcomes. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | DONE / NO-OP_ALREADY_DONE | PM -> PA/CC -> PM | Durable learning SSOT selected. | Report `2026-06-24--learning_ssot_decision_packet.md`; artifact `probe_ledger.jsonl` remains current SSOT. | No-repeat unless SSOT source/runtime/PG/artifact evidence changes. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | DONE / NO-OP_ALREADY_DONE | PM -> PA/E1 -> E2 -> E4 -> PM | Learning output becomes reviewable proposal only; no direct order/risk/live mutation. | Report `2026-06-24--autonomous_parameter_proposal_contract.md`. | No-repeat unless proposal contract source/runtime/artifact evidence changes. |
| `P1-RUNTIME-HEALTH-HYGIENE-LOCAL-LINEAGE-68-STALE-WORKING` | 1 | DONE / NO-OP_ALREADY_DONE | PM -> E2 -> E4 -> PM | [68] keeps normal entry exposure fail-closed and classifies narrow local close/risk stale rows as visible residuals. | Report `2026-06-26--health68_local_lineage_residual_source_patch.md`; tests `30 passed`. | No-repeat unless [68] source/runtime evidence changes. |
| `P1-RUNTIME-HEALTH-HYGIENE-68-RUNTIME-SYNC-REVIEW` | 1 | DONE_WITH_CONCERNS | PM -> E3 -> PM | Linux source-only fast-forward to [68] fix; no restart/rebuild/env/crontab/PG/Bybit mutation; direct [68] check passes. | Report `2026-06-26--health68_runtime_source_sync_review.md`; Linux `HEAD=0246b263`, direct [68] `PASS`. | No-repeat. Cron expected-head drift is now separately closed below. |
| `P1-RUNTIME-HEALTH-HYGIENE-CRON-EXPECTED-HEAD-DRIFT-REVIEW` | 1 | DONE_WITH_CONCERNS | PM -> E3 -> PM | Replace only exact expected-head SHA literals; preserve line count, schedules, wrappers, logs, env flags, services, and authority posture. | Runtime audit `/tmp/openclaw/audit/crontab_expected_head_sync_20260626T041735Z`; old count `0`, new count `11`, line count `70`. | No-repeat unless runtime source head or crontab evidence changes. |
| `P1-RUNTIME-HEALTH-HYGIENE-CRON-POST-ALIGNMENT-HYGIENE-SNAPSHOT` | 1 | WAITING / PAUSED_BY_OPERATOR_REQUEST | PM -> E3/PM | Produce a no-mutation read-only hygiene snapshot using current source, crontab, user API service, and selected artifact mtimes; do not overwrite `_latest`, restart services, edit crontab/env, write PG, or call Bybit. | Not started because operator requested pause after this round. | On resume: collect supplied snapshots and run `helper_scripts/cron/runtime_health_hygiene.py` read-only; stop if it requires runtime mutation. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | DEFERRED | PM -> BB/E2/E4 -> PM | Production full-scan pagination adoption path recorded and reviewed. | Mac source has full-scan helper; runtime source may include it via `0246b263`, but no exchange-facing use is authorized here. | Carry into a future exchange-inventory/reconciler blocker only if needed. |

## §3 Hard Gates

| Gate | Trigger | Rule |
|---|---|---|
| Runtime source sync | Any Linux checkout/source update. | Requires separate PM -> E3 review; no restart/rebuild by default. |
| Crontab/env mutation | Any edit to crontab or persistent runtime env. | Requires PM -> E3 review with exact allowed diff. Current expected-head edit is closed; do not repeat without new evidence. |
| Authorization object | Any move from defer/review packet to granted bounded Demo probe. | Requires exact typed confirm or valid structured standing Demo authorization scoped to `grid_trading|AVAXUSDT|Sell`, max `1`, TTL `<=4h`, demo only. |
| Runtime/order path | Any public/private Bybit call, adapter/writer enablement, plan mutation, or order submission. | Requires fresh PM -> E3 -> BB -> PM order-envelope/runtime-source/reconciliation review. No current authority exists. |
| Cost Gate | Any attempt to reduce global Cost Gate or treat a row as proof. | Global Cost Gate must not be lowered. Proof must be candidate-matched and include fills, fees, slippage, lineage, controls, and execution realism. |
| Live/mainnet | Any mainnet key/order/path. | Out of scope; no live authority. |

## §4 Safety Invariants And Proof Exclusions

- Profit is optimized only inside survival, Guardian/risk gates, Decision Lease, Rust authority, authorization gates, auditability, and reconstructability.
- Do not lower global Cost Gate, widen caps/freshness gates, fake freshness, or bypass Guardian/risk/Decision Lease/Rust authority.
- `flash_dip_buy` demo fills, cleanup/risk-close fills, unattributed fills, local stale Working rows, artifact counts, source-smoke, single-window MM positives, and replay-only results cannot count as Cost Gate, bounded-probe, promotion, or risk-adjusted net PnL proof.
- Learning output may become a reviewable proposal only; it must not directly mutate order/risk/live state.

## §5 Aggressive Alpha Backlog

| Hypothesis | Score snapshot | Why it might make money | Fastest safe test | Required data | Failure condition | Authority |
|---|---|---|---|---|---|---|
| AVAX false-negative near-touch bounded Demo | upside High; evidence Medium; realism Medium; cost Good; time Fast; account risk Low if capped; governance risk Medium; autonomy High | Historic blocked outcomes clear current modeled cost by a wide margin; near-touch-or-skip may convert false-negative edge into real candidate-matched fills. | Admit machine-checkable bounded Demo authorization, then fresh E3/BB order-envelope review for one capped post-only near-touch-or-skip attempt. | Valid authorization object, fresh BBO, cap/min-notional, order/fill/fee/slippage lineage, matched blocked controls. | No touch, taker fill, stale BBO, missing lineage, net after fees/slippage <= 0, or control underperforms. | Structured bounded Demo authorization + E3/BB required. |
| Cron/source false-blocker reduction | upside Medium; evidence High; realism High; cost Neutral; time Fast; account risk Low; governance Low; autonomy Medium | Removing source-head mismatch lets scheduled learning/health artifacts fail on real issues instead of stale metadata. | On resume, read-only hygiene snapshot from current crontab/source/user API service/artifact mtimes. | Runtime source head, crontab snapshot, user API service state, selected artifact mtimes, no-authority hygiene packet. | Snapshot shows authority/proof contamination, source drift, or service/crontab mutation requirement. | Read-only PM/E3 hygiene snapshot; no restart/order. |
| Current-fee maker/MM repeat-window branch | upside Medium; evidence Low; realism Low-Medium; cost Tight; time Medium; account risk None source-only; governance Low; autonomy Medium | Repeated maker-positive windows could become a low-cost execution path without lowering Cost Gate. | Accumulate independent current-fee windows and maker-realism score without claiming proof. | Recent maker/taker fees, queue proxies, spread/markout, distinct dates, matched controls. | Single-window only, net cushion below fees/slippage, or maker ratio cannot be achieved. | Research/proposal only. |

## §6 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--cron_expected_head_drift_alignment.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T041121Z_cron_expected_head_drift_review.json | sed -n '1,220p'
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && git rev-parse HEAD && git status --short && crontab -l | grep -o "0246b26361e403e6cb1ddd126eba8e3cd7b91a23" | wc -l'
ssh trade-core 'systemctl --user is-active openclaw-trading-api.service && systemctl --user show openclaw-trading-api.service -p MainPID --value'
ssh trade-core 'systemctl --user is-active openclaw-watchdog.service && systemctl --user is-enabled openclaw-watchdog.service'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
