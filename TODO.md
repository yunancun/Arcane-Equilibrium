# Xuanheng TODO - Active Dispatch Queue

**Version** v576 | **Date** 2026-06-26
**Source/runtime pointer**: source/origin `beeef498206bb4b4ddc80e957445e56b12688fd0`; runtime `trade-core` clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74` as of `2026-06-26T11:04:00Z`; no runtime/source/crontab/service apply in v576.
**Current posture**: P0 auth is still blocked by missing candidate-scoped authorization. Runtime source-sync no-apply review is done; future sync is not needed immediately and would require a separate apply checkpoint.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--runtime_source_sync_review_no_apply.md`; latest Operator note `docs/CCAgentWorkSpace/Operator/2026-06-26--runtime_source_sync_review_no_apply.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Facts That Affect Dispatch

| Fact | Value | Dispatch impact |
|---|---|---|
| Runtime source/services | `2026-06-26T11:04:00Z`: runtime source clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74`; API MainPID `2218842`. | v576 did not sync runtime, edit crontab, run cron, or restart service. |
| Runtime expected-head pins | `2026-06-26T11:04:00Z`: 11 active cron expected-head literals still pin `dd22810ee41c353c1d214d9a3217862d7b2bac74`. | Runtime is internally consistent. If a future sync is opened, source fast-forward and all 11 expected-head pins must move in one reviewed checkpoint. |
| Bounded authorization | Runtime latest auth sha `167af6133af27fbe2476a55184608c8ae7fb35b8d1aff8bf45fedfab9ad4ebf2`; status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`; AVAX candidate; `decision=defer`; no auth object or active authority. | P0 bounded probe authorization remains blocked. Broad Demo API intent is not a repo-valid order/probe grant. |
| Source/runtime diff | E3 no-apply review: no changed cron/Rust/API/deploy files; changed files are docs/state, manual research helpers, and tests. | No immediate apply needed. Future source sync has no security blocker but must not run manual public quote helpers. |
| Fresh AVAX source/no-order preview | Reroute sha `bc300277...`; atomic runner summary sha `98c7d75...`; construction preview sha `f721bc3...`. | Evidence-only. Do not repeat quote/preview work without new E3/BB-reviewed evidence delta. |

## §1 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | PM -> E3 -> BB -> PM | Candidate-scoped bounded Demo authorization only; no global Cost Gate lowering; no live; no order/probe authority unless a valid scoped authorization is admitted and E3/BB review passes. | Auth sha `167af613...` has no authorization object and no active authority. | Resume only on real candidate-scoped auth object, exact typed confirm, or standing-auth delta that passes repo gates. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills with fees/slippage, controls, execution realism, and repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe produces candidate-matched outcomes. |
| `P1-RUNTIME-HEALTH-HYGIENE-SOURCE-SYNC-APPLY-REVIEW` | 1 | DEFERRED | PM -> E3 -> PM | If opened, apply exact source sync envelope only: fast-forward runtime source and update all 11 expected-head pins together, then post-check clean head/pin counts/API PID/auth unchanged. | E3 no-apply review found no blocker and no immediate need. | Do not run by default. Open only if operator/PM explicitly decides runtime needs v574/v575/v576 source availability. |

## §2 Closed Markers To Prevent Rework

| ID | Status | Latest report | No-repeat rule |
|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md` | Reopen only on new exchange inventory, fill attribution, or proof-quality evidence. |
| `P0-PROFIT-CANDIDATE-SELECTION` | DONE_WITH_CONCERNS | AVAX Sell candidate selected; v574 construction preview ready no order. | Reopen only if fresh evidence invalidates AVAX cap feasibility or ranking. |
| `P1-LEARNING-LOOP-CLOSURE` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--learning_ssot_decision_packet.md` | No-op already done: artifact `probe_ledger.jsonl` is current SSOT; PG-backed cutover is not current. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--autonomous_parameter_proposal_contract.md` | No-op already done: learning output becomes inactive review packet only, never direct order/risk/live mutation. |
| `P1-RUNTIME-HEALTH-HYGIENE-SOURCE-SYNC-REVIEW-NO-APPLY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--runtime_source_sync_review_no_apply.md` | No-op unless a new source/runtime delta appears or an apply checkpoint is explicitly opened. |
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
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--runtime_source_sync_review_no_apply.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T110400Z_runtime_source_sync_review_no_apply.json
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && git rev-parse HEAD && git status --short'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: The next PM can identify the next action in under one minute: P0 auth only on real scoped auth delta; runtime sync apply is deferred and must be a separate reviewed checkpoint.
