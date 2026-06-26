# Xuanheng TODO - Active Dispatch Queue

**Version** v588 | **Date** 2026-06-26
**Source/runtime pointer**: source snapshot before this TODO commit `e590ac2ca0ef51ed23fb98dbccafd135b8381674`; runtime `trade-core` read-only source head `b224c759200d8dfc6fc4a53cbee39b8fb3683118` as of `2026-06-26T14:00:04Z`.
**Current posture**: P0 bounded Demo authorization remains blocked; current round closed source-only regime/OOS label contract and then pauses by operator request. No private fee read, Bybit order/cancel/modify, PG query/write, runtime/service/env/crontab mutation, Cost Gate lowering, or authority/proof claim was performed.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--regime_oos_label_contract_no_order.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Facts That Affect Dispatch

| Fact | Value | Dispatch impact |
|---|---|---|
| Operator pause | After this round, stop and keep TODO compliant before further loop work. | Do not auto-advance to the next blocker in this session. Resume only on a new operator message. |
| Runtime source | Runtime checkout read-only pointer remains clean at `b224c759200d8dfc6fc4a53cbee39b8fb3683118` on `2026-06-26T14:00:04Z`. | No runtime source sync is justified by this docs/source-only helper batch. |
| Bounded authorization artifact | `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json`, sha `6d3016328c2673fd3a408b4bfa87c3a4d78f99377f28bee4e6fdb9a52561f52e`, mtime `2026-06-26T14:00:04.637727Z`; status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`; candidate `grid_trading|AVAXUSDT|Sell`; `decision=defer`; no `authorization_id`, typed confirm, probe authority, or order authority. | P0 authorization remains blocked. Broad chat approval is not a machine-checkable scoped auth object. |
| Regime/OOS label contract | Source-only smoke `/tmp/openclaw/regime_oos_label_contract_smoke_20260626T1420Z/regime_oos_label_contract.json`, sha `739f684258bf1b21ba26f44b1cf964f54a46eee94a5f31f7b9c949b0c3c8a9a7`, status `REGIME_OOS_LABEL_CONTRACT_READY_NO_AUTHORITY`. | Future AVAX proof must attach leak-free PIT regime, market-anchor/overlay, freshness bucket, recent 90d/180d net fields, survivorship/breadth, repeat/OOS, purge/embargo, `n_independent`, `sample_unit`, verdict/reject labels. This is not proof or order admission. |
| Session state | `/tmp/openclaw/session_loop_state_20260626T1420Z_regime_oos_label_contract_no_order.json`, sha `de4617f7e0eb6b3860266c1f68d38b3d71f42eb0cc79f7c61698e8a7ddef46f4`. | Current round started with explicit anti-repeat state; P0 had no admitted auth delta, so a source-only unclosed proof gap was selected. |
| Verification | Focused regime/OOS tests `9 passed`; adjacent gap/control/regime tests `20 passed`; `py_compile` passed; `git diff --check` passed; PA `DONE_WITH_CONCERNS`; E2 re-check `DONE`; E4 final rerun `DONE`. | Source helper is locally verified. |

## §1 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `PAUSED-AFTER-V588-OPERATOR-REQUEST` | 0 | WAITING | PM | Resume only after operator asks to continue. | Current operator request: run this round, then pause and fix TODO compliance. | Stop after v588 report/commit/push. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | PM -> E3 -> BB -> PM | Candidate-scoped bounded Demo authorization only; no global Cost Gate lowering; no live; no order/probe authority unless a valid scoped authorization object or valid exact typed confirm is admitted and E3/BB review passes. | Latest runtime auth sha `6d301632...` remains `decision=defer`, no `authorization_id`, no typed confirm, no probe/order authority. | On resume, check for a real candidate-scoped auth delta; otherwise no-op and do not rerun read-only auth audits. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills with fees/slippage, controls, execution realism, and repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe produces candidate-matched outcomes. |
| `P1-FEE-TIER-PRIVATE-READ-RUNTIME-INVOKE-AUTHORIZATION` | 1 | BLOCKED | PM -> E3 -> BB -> PM | Any actual private fee-rate read requires a fresh one-shot runtime action: exact `AVAXUSDT`, no argv secrets, bounded timeout/no redirects, strict exact-row parser, sanitized artifact only, no PG write, no runtime fee-cache replacement, no proof/authority use. | v585 envelope is READY_NO_READ; no private read has been executed. | Stop unless a later checkpoint explicitly opens and reviews the one-shot private read action. |

## §2 Closed No-Repeat Markers

| ID | Status | Latest report | No-repeat rule |
|---|---|---|---|
| `P1-AGGRESSIVE-ALPHA-REGIME-OOS-LABEL-CONTRACT-NO-ORDER` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--regime_oos_label_contract_no_order.md` | Do not rerun on the same gap/control/auth artifacts. Reopen only if candidate identity, ADR-0047 evidence rules, label schema, or a real auth/runtime data-access scope changes. |
| `P1-AGGRESSIVE-ALPHA-AVAX-SOURCE-ONLY-LADDER` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--candidate_source_freshness_alignment_atomic_preview_runner.md` | Compact ladder is closed through low-price ranking, evidence-floor gap closure, control identity, current cap/risk, fee/slippage, fresh BBO, maker policy, public quote packet/capture, quote adapter, atomic preview runner, fee-tier/maker-ratio, private fee read envelope design/review, and regime/OOS label contract. Reopen only on changed candidate identity, fee/freshness/regime policy, source/runtime evidence delta, or reviewed exchange-facing scope. |
| `P0-PROFIT-EVIDENCE-QUALITY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md` | Reopen only on new exchange inventory, fill attribution, or proof-quality evidence. Unattributed/cleanup fills still never count as promotion or bounded-probe proof. |
| `P0-PROFIT-CANDIDATE-SELECTION` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--profit_candidate_selection_avax_review_packet.md` | AVAX Sell remains the current cap-feasible bounded Demo review candidate unless fresh evidence invalidates cap feasibility or ranking. |
| `P1-FEE-TIER-PRIVATE-READ-ENVELOPE-E3-BB-REVIEW-NO-READ` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--private_fee_tier_read_envelope_e3_bb_review_no_read.md` | Source-only envelope is reviewed and hardened, but actual private read remains blocked until separately opened through PM -> E3 -> BB. |
| `P1-RUNTIME-HEALTH-HYGIENE-AUTH-TYPED-CONFIRM-GUARD-RUNTIME-SYNC-APPLY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--auth_typed_confirm_guard_runtime_sync_apply.md` | Runtime source is `b224c759`; expected-head pins were aligned. Do not repeat for docs/TODO/report/SCRIPT_INDEX drift. |
| `P1-LEARNING-LOOP-CLOSURE` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--learning_ssot_decision_packet.md` | Artifact `probe_ledger.jsonl` remains current SSOT; PG-backed cutover is not current. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--autonomous_parameter_proposal_contract.md` | Learning output becomes inactive review packet only, never direct order/risk/live mutation. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Profit priority | Optimize real risk-adjusted net PnL after fees/slippage only inside survival, Guardian/risk, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| Authorization | A changed defer artifact or broad chat approval is not bounded-probe/order authority. Candidate-scoped bounded Demo grant requires a valid structured auth object or valid exact typed confirm after fixed runtime/preflight readiness plus E3/BB review. |
| Runtime/order path | Private/trading Bybit calls, order submit/cancel/modify, PG write, adapter/writer enablement, plan mutation, crontab/env edit, and service restart require reviewed runtime chain. |
| Cost Gate | Do not lower global Cost Gate or freshness gate. Proof must be candidate-matched and include actual fills, fees, slippage, lineage, controls, regime/OOS labels, and execution realism. |
| Live/mainnet | Out of scope; Demo experience must be reconstructable and portable for later live review, but cannot bypass live gates. |

## §4 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
git -C /Users/ncyu/Projects/TradeBot/srv rev-parse HEAD
sed -n '1,180p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
sed -n '1,240p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--regime_oos_label_contract_no_order.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T1420Z_regime_oos_label_contract_no_order.json
python3 -m json.tool /tmp/openclaw/regime_oos_label_contract_smoke_20260626T1420Z/regime_oos_label_contract.json | sed -n '1,220p'
PYTHONPATH=/Users/ncyu/Projects/TradeBot/srv/helper_scripts/research python3 -m pytest -q \
  /Users/ncyu/Projects/TradeBot/srv/helper_scripts/research/tests/test_cost_gate_regime_oos_label_contract.py \
  /Users/ncyu/Projects/TradeBot/srv/helper_scripts/research/tests/test_cost_gate_source_only_control_identity_contract.py \
  /Users/ncyu/Projects/TradeBot/srv/helper_scripts/research/tests/test_cost_gate_false_negative_evidence_floor_gap_closure.py
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: The next PM can identify the next action in under one minute: this session is paused; on resume check only for a real P0 auth delta, otherwise do not repeat closed AVAX source-only ladder work.
