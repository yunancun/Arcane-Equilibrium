# Xuanheng TODO - Active Dispatch Queue

**Version** v575 | **Date** 2026-06-26
**Source/runtime pointer**: source/origin `26a203baf88524d02de294e1840ba74ffb55750f`; runtime `trade-core` clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74` as of `2026-06-26T10:57:23Z`; no runtime/source/crontab/service apply in v575.
**Current posture**: P0 auth is still blocked by missing candidate-scoped authorization. P1 learning SSOT and autonomous proposal are already DONE/no-repeat; the only source-only next item is runtime-hygiene source-sync review with no apply.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--antirepeat_todo_runtime_hygiene_reconcile_no_apply.md`; latest Operator note `docs/CCAgentWorkSpace/Operator/2026-06-26--antirepeat_todo_runtime_hygiene_reconcile_no_apply.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Facts That Affect Dispatch

| Fact | Value | Dispatch impact |
|---|---|---|
| Runtime source/services | `2026-06-26T10:57:23Z`: runtime source clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74`; API MainPID `2218842`. | v575 did not sync runtime, edit crontab, or restart service. |
| Runtime expected-head pins | `2026-06-26T10:57:23Z`: 11 active cron expected-head literals still pin `dd22810ee41c353c1d214d9a3217862d7b2bac74`. | Runtime is internally consistent, but behind source/origin `26a203b...`; sync requires separate E3 runtime review and no implicit apply. |
| Bounded authorization | Runtime latest auth sha `c956288b1b5070132cac0223f2806e03dee44eeae0b7a20adfee86542d5aa0df`; status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`; AVAX candidate; `decision=defer`; no auth object or active authority. | P0 bounded probe authorization remains blocked. Broad Demo API intent is not a repo-valid order/probe grant. |
| Fresh AVAX source/no-order preview | Reroute sha `bc300277...`; atomic runner summary sha `98c7d75...`; construction preview sha `f721bc3...`. | Evidence-only. Do not repeat quote/preview work without new E3/BB-reviewed evidence delta. |
| Proof exclusions | Exclude unattributed fills, cleanup/risk-close fills, stale local `Working` rows, `flash_dip_buy`, cross-symbol controls, artifact counts, source-smoke, replay-only results, public quotes, adapter snapshots, and no-order previews. | These never count toward promotion or risk-adjusted net PnL proof. |

## §1 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | PM -> E3 -> BB -> PM | Candidate-scoped bounded Demo authorization only; no global Cost Gate lowering; no live; no order/probe authority unless a valid scoped authorization is admitted and E3/BB review passes. | Auth sha `c956288b...` has no authorization object and no active authority. | Resume only on real candidate-scoped auth object, exact typed confirm, or standing-auth delta that passes repo gates. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills with fees/slippage, controls, execution realism, and repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe produces candidate-matched outcomes. |
| `P1-RUNTIME-HEALTH-HYGIENE-SOURCE-SYNC-REVIEW-NO-APPLY` | 1 | READY | PM -> E3 -> PM | Decide whether source/origin `26a203b...` needs runtime source/expected-head sync; produce review only unless a separate apply action is explicitly opened. | Runtime head and cron pins remain `dd22810e`; source/origin is `26a203b...`; v574 helper/report changes are not runtime-applied. | If continuing without auth delta, do E3 no-apply review. Do not git pull runtime, edit crontab, restart service, or run cron in this item. |

## §2 Closed Markers To Prevent Rework

| ID | Status | Latest report | No-repeat rule |
|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md` | Reopen only on new exchange inventory, fill attribution, or proof-quality evidence. |
| `P0-PROFIT-CANDIDATE-SELECTION` | DONE_WITH_CONCERNS | AVAX Sell candidate selected; v574 construction preview ready no order. | Reopen only if fresh evidence invalidates AVAX cap feasibility or ranking. |
| `P1-LEARNING-LOOP-CLOSURE` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--learning_ssot_decision_packet.md` | No-op already done: artifact `probe_ledger.jsonl` is current SSOT; PG-backed cutover is not current. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--autonomous_parameter_proposal_contract.md` | No-op already done: learning output becomes inactive review packet only, never direct order/risk/live mutation. |
| `P1-AGGRESSIVE-ALPHA-CANDIDATE-SOURCE-FRESHNESS-ALIGNMENT-NO-CAPTURE` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--candidate_source_freshness_alignment_atomic_preview_runner.md` | Do not repeat source alignment or public quote runner without new source/runtime/artifact delta and E3/BB review for exchange-facing work. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Profit priority | Optimize real risk-adjusted net PnL after fees/slippage only inside survival, Guardian/risk, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| Authorization | Broad Demo API permission is not bounded-probe/order authority. Candidate-scoped bounded Demo grant requires a valid structured auth object or exact typed confirm plus E3/BB review. |
| Runtime/order path | Private/trading Bybit calls, order submit/cancel/modify, PG write, adapter/writer enablement, plan mutation, crontab/env edit, and service restart require reviewed runtime chain. |
| Cost Gate | Do not lower global Cost Gate or freshness gate. Proof must be candidate-matched and include actual fills, fees, slippage, lineage, controls, and execution realism. |
| Quote/adapter/preview | Public quote, adapter snapshot, and no-order construction preview are evidence-only, not order admission or profit proof. |
| Live/mainnet | Out of scope; no live/mainnet authority. |

## §4 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,180p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--antirepeat_todo_runtime_hygiene_reconcile_no_apply.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T105722Z_antirepeat_todo_runtime_hygiene_reconcile.json
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && git rev-parse HEAD && git status --short'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: The next PM can identify the next action in under one minute: P0 auth only on real scoped auth delta; otherwise the next safe item is E3 no-apply runtime source-sync review.
