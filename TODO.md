# Xuanheng TODO - Active Dispatch Queue

**Version** v544 | **Date** 2026-06-26
**Repo/runtime pointer**: Mac/origin `main` was clean at docs checkpoint `65fe28ef5a74b89bf624e4b858884c4774a47f67` before this docs checkpoint. Linux runtime `trade-core` remains source-clean at runtime code checkpoint `0246b26361e403e6cb1ddd126eba8e3cd7b91a23`.
**Current posture**: `P1-RUNTIME-HEALTH-HYGIENE-CRON-POST-ALIGNMENT-HYGIENE-SNAPSHOT` is closed `DONE_WITH_CONCERNS`; next blocker is `P0-BOUNDED-PROBE-AUTHORIZATION`, still blocked until a machine-checkable bounded Demo authorization object or exact typed confirm exists.
**Links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--runtime_health_hygiene_post_alignment_snapshot.md`; version changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime hygiene packet | `2026-06-26T04:34:19Z` packet `/tmp/openclaw/runtime_health_hygiene_post_alignment_20260626T042802Z/runtime_health_hygiene_post_alignment.json` is `RUNTIME_HEALTH_HYGIENE_CLEAN_SOURCE_ONLY`; operator action required `false`. | Runtime hygiene false-blocker lane is clean. This is not profit/probe proof and does not grant authority. |
| Runtime source | Snapshot source JSON: Linux `/home/ncyu/BybitOpenClaw/srv` `HEAD=0246b26361e403e6cb1ddd126eba8e3cd7b91a23`, worktree status count `0`, `RUNTIME_SOURCE_ALIGNED`. | Runtime has the [68] local-lineage source fix. Docs/TODO-only commits above `0246b263` do not imply runtime sync. |
| Cron expected-head | Snapshot crontab: line count `70`, old literal `d2cd70d0...` count `0`, new literal `0246b263...` count `11`, matching lines `57,67,68,69,70`, packet status `CRON_EXPECTED_HEAD_CONSISTENT`. | Source-mismatch noise from stale cron pins is removed. Do not repeat the crontab edit without new evidence. |
| Runtime authority flags | Same crontab check: `OPENCLAW_ALLOW_MAINNET=1` count `0`, `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED` count `0`, `RECORD_PROBE_OUTCOMES=1` count `0`, `OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=0` count `1`. | No live/mainnet, adapter, probe-outcome recording, or Cost Gate authority was enabled. |
| API/watchdog services | Correct user-service scope snapshot: `openclaw-trading-api.service` active/enabled, MainPID `2218842`, `NRestarts=0`; `openclaw-watchdog.service` active/enabled, MainPID `1538268`; packet status `API_SERVICE_OWNERSHIP_ALIGNED`. | Use `systemctl --user` checks for API/watchdog ownership. Do not create a false blocker from wrong systemd scope. |
| Canonical learning artifacts | Reduced compatibility snapshot is clean. `mm_current_fee_confirmation_latest` refreshed `2026-06-26T04:30:05Z`, status `NO_CURRENT_FEE_POSITIVE_MM_CELL`; `false_negative_candidate_friction_scorecard_latest` refreshed `2026-06-26T04:30:54Z`, status `FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY`. | Current-fee/MM path is not the fastest positive current-fee branch now. False-negative AVAX path remains the main review-only alpha candidate. |
| Selected candidate | Review-only candidate remains `grid_trading|AVAXUSDT|Sell`, 60m, avg modeled net `73.5511bps`, `48/48` net-positive, cap `10 USDT`, min notional `5 USDT`. | Candidate selection is closed. Do not reselect without new candidate/cap/fee/touchability evidence. |
| Bounded authorization | Latest AVAX packet is review-ready/defer-only with no authorization object, no active runtime probe/order authority, and no Cost Gate adjustment. Broad chat authorization is not a machine-checkable bounded-probe grant. | Actual bounded Demo execution remains blocked until a valid structured standing Demo authorization or exact typed confirm is admitted, then E3/BB order-envelope review passes. |
| Proof exclusions | `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale rows, artifact counts, source-smoke, single-window MM positives, and replay-only results remain proof-excluded. | These cannot count toward bounded-probe proof, Cost Gate proof, promotion evidence, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T042802Z_cron_post_alignment_hygiene_snapshot.json` |
| `active_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-CRON-POST-ALIGNMENT-HYGIENE-SNAPSHOT` |
| `blocker_goal` | Produce a no-mutation read-only runtime hygiene snapshot after expected-head alignment, using current source, crontab, user API/watchdog service, and reduced artifact compatibility evidence. |
| `profit_relevance` | A clean hygiene surface prevents stale metadata from blocking bounded Demo candidate review and lets learning focus on real edge/execution/proof quality. |
| `previous_evidence_checked` | Reports `2026-06-26--cron_expected_head_drift_alignment.md`, `2026-06-26--health68_runtime_source_sync_review.md`, and `2026-06-24--runtime_health_hygiene_final_snapshot.md`. |
| `new_evidence_delta_required` | Post-alignment supplied-snapshot hygiene packet must prove current source/crontab/user-service/artifact state is clean or expose a concrete non-mutating blocker. |
| `new_evidence_delta_found` | E3 allowed read-only snapshots only. Packet is `RUNTIME_HEALTH_HYGIENE_CLEAN_SOURCE_ONLY`; source/crontab/API/artifact compatibility are clean; no authority/proof/mutation contamination. Natural artifact delta: MM current-fee now reports `NO_CURRENT_FEE_POSITIVE_MM_CELL`; false-negative scorecard remains ready. |
| `anti_repeat_decision` | `CRON-EXPECTED-HEAD-DRIFT-REVIEW` -> `NO-OP_ALREADY_DONE`; proceeded to new post-alignment snapshot evidence. Did not rerun crontab edit, [68] sync, or P0 authorization audit. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION` |
| `why_not_repeating_current_blocker` | Post-alignment hygiene packet is clean. Repeating it without new source/crontab/service/artifact delta would violate anti-repeat. |

## §2 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE_WITH_CONCERNS | PM -> E3/BB/QC -> PM | Deep/open demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | Clean exchange-book report `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; proof exclusions carried in §0/§4. | No-repeat unless new exchange inventory, fills attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE_WITH_CONCERNS | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority; proof exclusions recorded. | Report `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading|AVAXUSDT|Sell`. | No-repeat unless new candidate/cap/fee/touchability evidence appears. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | PM -> E3 -> BB -> Operator/QC -> PM | Candidate-specific bounded Demo authorization only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless exact bounded authorization is admitted and E3/BB review passes. | Report `2026-06-26--avax_authorization_review_ready_no_authority.md`; no authorization object. Broad chat permission is operational intent, not a machine-checkable runtime grant. | Stop before orders. Do not rerun the no-authority audit unless a valid `standing_demo_operator_authorization_v1` or exact typed confirm for `grid_trading|AVAXUSDT|Sell`, max `1`, TTL `<=4h`, appears; then run fresh E3/BB order-envelope/runtime review. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Wait condition: only after an authorized bounded Demo probe with candidate-matched outcomes. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | DONE / NO-OP_ALREADY_DONE | PM -> PA/CC -> PM | Durable learning SSOT selected. | Report `2026-06-24--learning_ssot_decision_packet.md`; artifact `probe_ledger.jsonl` remains current SSOT. | No-repeat unless SSOT source/runtime/PG/artifact evidence changes. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | DONE / NO-OP_ALREADY_DONE | PM -> PA/E1 -> E2 -> E4 -> PM | Learning output becomes reviewable proposal only; no direct order/risk/live mutation. | Report `2026-06-24--autonomous_parameter_proposal_contract.md`. | No-repeat unless proposal contract source/runtime/artifact evidence changes. |
| `P1-RUNTIME-HEALTH-HYGIENE-LOCAL-LINEAGE-68-STALE-WORKING` | 1 | DONE / NO-OP_ALREADY_DONE | PM -> E2 -> E4 -> PM | [68] keeps normal entry exposure fail-closed and classifies narrow local close/risk stale rows as visible residuals. | Report `2026-06-26--health68_local_lineage_residual_source_patch.md`; tests `30 passed`. | No-repeat unless [68] source/runtime evidence changes. |
| `P1-RUNTIME-HEALTH-HYGIENE-68-RUNTIME-SYNC-REVIEW` | 1 | DONE_WITH_CONCERNS | PM -> E3 -> PM | Linux source-only fast-forward to [68] fix; no restart/rebuild/env/crontab/PG/Bybit mutation; direct [68] check passes. | Report `2026-06-26--health68_runtime_source_sync_review.md`; Linux `HEAD=0246b263`, direct [68] `PASS`. | No-repeat. Cron expected-head drift is now separately closed below. |
| `P1-RUNTIME-HEALTH-HYGIENE-CRON-EXPECTED-HEAD-DRIFT-REVIEW` | 1 | DONE_WITH_CONCERNS / NO-OP_ALREADY_DONE | PM -> E3 -> PM | Replace only exact expected-head SHA literals; preserve line count, schedules, wrappers, logs, env flags, services, and authority posture. | Runtime audit `/tmp/openclaw/audit/crontab_expected_head_sync_20260626T041735Z`; old count `0`, new count `11`, line count `70`. | No-repeat unless runtime source head or crontab evidence changes. |
| `P1-RUNTIME-HEALTH-HYGIENE-CRON-POST-ALIGNMENT-HYGIENE-SNAPSHOT` | 1 | DONE_WITH_CONCERNS | PM -> E3 -> PM | Produce a no-mutation read-only hygiene snapshot using current source, crontab, user API service, and selected artifact mtimes; do not overwrite `_latest`, restart services, edit crontab/env, write PG, or call Bybit. | Report `2026-06-26--runtime_health_hygiene_post_alignment_snapshot.md`; packet `/tmp/openclaw/runtime_health_hygiene_post_alignment_20260626T042802Z/runtime_health_hygiene_post_alignment.json` is clean. | No-repeat unless source/crontab/user-service/artifact evidence changes. |
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
| AVAX false-negative near-touch bounded Demo | upside High; evidence Medium; realism Medium; cost Good; time Fast after auth; account risk Low if capped; governance risk Medium; autonomy High | Historic blocked outcomes clear current modeled cost by a wide margin; false-negative scorecard remains ready while current-fee MM no longer shows a positive current-fee cell. | Admit machine-checkable bounded Demo authorization, then fresh E3/BB order-envelope review for one capped post-only near-touch-or-skip attempt. | Valid authorization object, fresh BBO, cap/min-notional, order/fill/fee/slippage lineage, matched blocked controls. | No touch, taker fill, stale BBO, missing lineage, net after fees/slippage <= 0, or control underperforms. | Structured bounded Demo authorization + E3/BB required. |
| False-negative subset mining under no-order mode | upside Medium-High; evidence Medium; realism Medium; cost Good; time Medium; account risk None source-only; governance Low; autonomy High | With MM current-fee positive cells absent, the fastest safe alpha expansion is to mine the false-negative scorecard for high-cushion subclusters without changing Cost Gate or orders. | Source-only scorecard slice by symbol/horizon/regime/placement feasibility; emit review-only proposal, no authority. | Latest false-negative scorecard, cap/min-notional, BBO/market metadata, blocked controls, fee/slippage estimates. | Edge concentrated in stale windows, cap infeasible, or candidate-matched execution realism remains absent. | Research/proposal only. |
| Hygiene-clean scheduled learning verification | upside Medium; evidence High; realism High; cost Neutral; time Fast; account risk Low; governance Low; autonomy Medium | Clean source/cron/service hygiene lets future scheduled artifacts be trusted for blocker selection instead of ignored as drift noise. | Let scheduled wrappers produce next natural artifacts; do not manually refresh `_latest` unless a separate reviewed blocker requires it. | Natural artifact mtimes/statuses, source head, crontab expected-head, no-authority answers. | New source drift, authority/proof contamination, or scheduled artifact failure not attributable to market data. | Read-only review only; no restart/order. |

## §6 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--runtime_health_hygiene_post_alignment_snapshot.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T042802Z_cron_post_alignment_hygiene_snapshot.json | sed -n '1,220p'
python3 -m json.tool /tmp/openclaw/runtime_health_hygiene_post_alignment_20260626T042802Z/runtime_health_hygiene_post_alignment.json | sed -n '1,180p'
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && git rev-parse HEAD && git status --short'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
