# Xuanheng TODO - Active Dispatch Queue

**Version** v579 | **Date** 2026-06-26
**Source/runtime pointer**: source/origin clean at `370a3d82984f49b394a9657a0552bad42f0ec325`; runtime `trade-core` clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74` as of `2026-06-26T11:54:34Z`; no runtime source sync, crontab edit, service restart, PG write, Bybit order action, or authority mutation in v579.
**Current posture**: v579 closes the runtime source-sync apply go/no-go review as read-only no-apply; P0 bounded authorization remains blocked by defer/no-authority artifacts; no unblocked source-only blocker is open.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--runtime_source_sync_apply_gonogo_no_apply.md`; latest Operator note `docs/CCAgentWorkSpace/Operator/2026-06-26--runtime_source_sync_apply_gonogo_no_apply.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Facts That Affect Dispatch

| Fact | Value | Dispatch impact |
|---|---|---|
| Runtime source/services | `2026-06-26T11:45:12Z`: runtime source clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74`. `systemctl --user` shows `openclaw-trading-api.service` loaded/active/running with MainPID `2218842`, and `openclaw-watchdog.service` loaded/active/running with MainPID `1538268`; `/proc/2218842/cgroup` is `app.slice/openclaw-trading-api.service`. System-level `systemctl` has no matching OpenClaw units, which is expected because these are user services. | The previous "manual uvicorn / service ownership not established" wording is stale/incomplete. API and watchdog ownership are established under user systemd. Do not repeat this audit unless unit state, PID ownership, or service files change. |
| Runtime expected-head pins | `2026-06-26T11:42:42Z`: 11 active cron expected-head literals still pin `dd22810ee41c353c1d214d9a3217862d7b2bac74` (`5 EXPECTED_HEAD`, `1 OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD`, `5 OPENCLAW_EXPECTED_SOURCE_HEAD`). | Runtime and cron pins remain internally consistent. A future source sync, if opened, must fast-forward runtime source and update all 11 expected-head pins together. |
| Source/runtime apply go/no-go | `dd22810e..370a3d82`: 26 commits / 67 files; categories are research helpers `12`, research tests `12`, PM reports `19`, Operator notes `19`, other docs `2`, TODO `1`, `.codex` `1`, script index `1`, other `0`. Runtime-sensitive scan for `rust/`, FastAPI `program_code/`, cron/canary/deploy/service/migration/Cargo paths returned no matches. | No immediate runtime source sync or expected-head crontab edit is justified. Reopen source-sync apply only if source drift includes runtime-scheduled/trading/control-plane files or PM explicitly opens an apply checkpoint. |
| Bounded authorization | Runtime latest auth sha `e7420e21f546845661dd2ba1841baf8d81f4af70e5241d6a4053cf40e74ab855`; status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`; AVAX candidate; `decision=defer`; no admitted probe/order authority fields. Latest shadow placement sha `265a16be...` is `SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH` with 50 reviewed orders, 40 shadow submits, and 0 candidate-matched orders. | P0 bounded probe authorization remains blocked. Shadow placement mismatch is a touchability design signal only, not authorization, proof, order admission, Cost Gate evidence, or promotion proof. |
| AVAX no-order construction | Construction preview sha `f721bc3a...`; atomic summary sha `98c7d75...`; reroute sha `bc300277...`; preview is no-order only. | Evidence-only. Do not repeat quote/preview work without new E3/BB-reviewed evidence delta. |
| AVAX cost-cushion worksheet | `/tmp/openclaw/maker_cost_cushion_worksheet_20260626T111710Z/maker_cost_cushion_worksheet.json`, sha `074d2e1dc1a17a86cc5d88fa9e71aaf97d35b9a098af6e5d318e8b30111f9ab1`; status `MAKER_COST_CUSHION_WORKSHEET_READY_NO_ORDER`; maker stress margin `66.9239bps`, taker failure-analysis margin `59.9239bps` under explicit research assumptions. | Supports future operator review packet only. It is not order admission, Cost Gate proof, promotion proof, or current account fee proof. |

## §1 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | PM -> E3 -> BB -> PM | Candidate-scoped bounded Demo authorization only; no global Cost Gate lowering; no live; no order/probe authority unless a valid scoped authorization is admitted and E3/BB review passes. | Auth sha `e7420e21...` remains `decision=defer`, no admitted authority. | Resume only on real candidate-scoped auth object, exact typed confirm, or standing-auth delta that passes repo gates. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills with fees/slippage, controls, execution realism, and repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe produces candidate-matched outcomes. |

## §2 Closed Markers To Prevent Rework

| ID | Status | Latest report | No-repeat rule |
|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md` | Reopen only on new exchange inventory, fill attribution, or proof-quality evidence. |
| `P0-PROFIT-CANDIDATE-SELECTION` | DONE_WITH_CONCERNS | AVAX Sell candidate selected; v574 construction preview ready no order. | Reopen only if fresh evidence invalidates AVAX cap feasibility or ranking. |
| `P1-LEARNING-LOOP-CLOSURE` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--learning_ssot_decision_packet.md` | No-op already done: artifact `probe_ledger.jsonl` is current SSOT; PG-backed cutover is not current. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--autonomous_parameter_proposal_contract.md` | No-op already done: learning output becomes inactive review packet only, never direct order/risk/live mutation. |
| `P1-AGGRESSIVE-ALPHA-CANDIDATE-SOURCE-FRESHNESS-ALIGNMENT-NO-CAPTURE` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--candidate_source_freshness_alignment_atomic_preview_runner.md` | Do not repeat source alignment or public quote runner without new source/runtime/artifact delta and E3/BB review for exchange-facing work. |
| `P1-RUNTIME-HEALTH-HYGIENE-SOURCE-SYNC-REVIEW-NO-APPLY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--runtime_source_sync_review_no_apply.md` | No-op unless a new source/runtime/auth delta appears or an apply checkpoint is explicitly opened. |
| `P1-AGGRESSIVE-ALPHA-MAKER-COST-CUSHION-WORKSHEET-NO-ORDER` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--maker_cost_cushion_worksheet_no_order.md` | Do not repeat unless fee assumptions, preview spread, candidate edge, or scoped auth evidence changes. |
| `P1-RUNTIME-HEALTH-HYGIENE-API-PROCESS-OWNERSHIP` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--api_process_ownership_readonly.md` | No-op unless `systemctl --user` unit state, API/watchdog PID ownership, service file, or runtime process cgroup changes. |
| `P1-RUNTIME-HEALTH-HYGIENE-SOURCE-SYNC-APPLY-GONOGO-NO-APPLY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--runtime_source_sync_apply_gonogo_no_apply.md` | No-op unless source drift includes runtime-scheduled/trading/control-plane/deploy files, runtime pins diverge internally, or PM explicitly opens an apply checkpoint. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Profit priority | Optimize real risk-adjusted net PnL after fees/slippage only inside survival, Guardian/risk, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| Authorization | A changed defer artifact is not bounded-probe/order authority. Candidate-scoped bounded Demo grant requires a valid structured auth object or exact typed confirm plus E3/BB review. |
| Runtime/order path | Private/trading Bybit calls, order submit/cancel/modify, PG write, adapter/writer enablement, plan mutation, crontab/env edit, and service restart require reviewed runtime chain. |
| Cost Gate | Do not lower global Cost Gate or freshness gate. Proof must be candidate-matched and include actual fills, fees, slippage, lineage, controls, and execution realism. |
| Quote/adapter/preview/worksheet | Public quote, adapter snapshot, no-order construction preview, and cost-cushion worksheet are evidence-only, not order admission or profit proof. |
| Live/mainnet | Out of scope; no live/mainnet authority. |

## §4 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
git -C /Users/ncyu/Projects/TradeBot/srv rev-parse HEAD
sed -n '1,180p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--runtime_source_sync_apply_gonogo_no_apply.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T115434Z_runtime_source_sync_apply_gonogo_no_apply.json
ssh trade-core 'systemctl --user show openclaw-trading-api.service -p Id -p ActiveState -p SubState -p MainPID -p FragmentPath -p UnitFileState --no-pager'
ssh trade-core 'python3 - <<'"'"'PY'"'"'
import json
p="/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json"
with open(p) as f:
    d=json.load(f)
print(d.get("status"), d.get("decision"), d.get("candidate"), d.get("probe_authority_granted"), d.get("order_authority_granted"))
PY'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: The next PM can identify the next action in under one minute: P0 auth resumes only on real scoped auth delta; no unblocked source-only blocker is currently open.
