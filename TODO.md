# Xuanheng TODO - Active Dispatch Queue

**Version** v582 | **Date** 2026-06-26
**Source/runtime pointer**: source/origin was `050566ec0ec52b03f9824ca498833d62303f8fc0` before the v582 docs update; final v582 commit is recorded in the PM response. Runtime `trade-core` is clean at `b224c759200d8dfc6fc4a53cbee39b8fb3683118` as of `2026-06-26T12:31:33Z`; runtime crontab expected-head pins old/target `0/11`.
**Current posture**: v582 applied the typed-confirm guard runtime sync. Natural auth artifact now suppresses exact typed-confirm while preflight/auth fields are incomplete, but P0 bounded authorization remains blocked by missing machine-checkable scoped authorization.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--auth_typed_confirm_guard_runtime_sync_apply.md`; latest Operator note `docs/CCAgentWorkSpace/Operator/2026-06-26--auth_typed_confirm_guard_runtime_sync_apply.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Facts That Affect Dispatch

| Fact | Value | Dispatch impact |
|---|---|---|
| Runtime source | `2026-06-26T12:31:33Z`: runtime source clean at `b224c759200d8dfc6fc4a53cbee39b8fb3683118`; local/origin `main` was `050566ec0ec52b03f9824ca498833d62303f8fc0` before this v582 docs update. | Runtime has the v580 typed-confirm source fix. Do not resync for docs-only drift unless a later runtime-affecting source delta appears. |
| Runtime expected-head pins | `2026-06-26T12:31:33Z`: crontab line count `70`; old `dd22810e...` count `0`; target `b224c759...` count `11`. Backup files: `/tmp/openclaw/runtime_hygiene_auth_typed_confirm_sync_20260626T123103Z/crontab.before` and `crontab.after`. | Expected-head pins are aligned with runtime source. Do not repeat this pin replacement. |
| Runtime services | `2026-06-26T12:31:33Z`: `openclaw-trading-api.service` user unit active/running MainPID `2218842`; `openclaw-watchdog.service` active/running MainPID `1538268`. | The sync did not restart services. Future deploy/restart still requires a separate reviewed path. |
| Bounded authorization artifact | Natural runtime auth artifact sha `fb2d05e8679c8005f2dde8987aaa133c8548e6d89c27fc7c347b20e2df69ff6a`, mtime `2026-06-26T12:30:51.185939Z`; status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`; candidate `grid_trading|AVAXUSDT|Sell`; `decision=defer`; no `authorization_id`, no probe/order authority; `typed_confirm_expected=None`; template `authorize_bounded_demo_probe:grid_trading|AVAXUSDT|Sell:<max_authorized_probe_orders<=3>:<authorization_id>`; readiness `PREFLIGHT_NOT_READY`. | Runtime review text is now fail-closed. This is still not authorization, order admission, Cost Gate proof, or promotion proof. |
| P0 auth gap | Artifact internals show `authority_patch_readiness.ready_for_operator_authorization=true` and `placement_repair_plan.ready_for_operator_authorization=true`, but `standing_demo_authorization.schema_valid=false`, `scope_valid=false`, `expiry_valid=false`, `status_active=false`, and `authorization_id=None`. | Next P0 transition requires a valid scoped authorization object or valid exact typed confirm. Do not treat broad chat approval, stale phrases, or defer artifacts as machine-checkable authority. |
| AVAX no-order evidence | Existing construction preview, cost-cushion worksheet, public quote/adapter path, and shadow placement data remain evidence-only. | They do not unlock P0 auth, order admission, Cost Gate proof, or promotion proof. Candidate-matched fills after scoped authorization are still required. |

## §1 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | PM -> E3 -> BB -> PM | Candidate-scoped bounded Demo authorization only; no global Cost Gate lowering; no live; no order/probe authority unless a valid scoped authorization object or valid exact typed confirm is admitted and E3/BB review passes. | Latest runtime auth sha `fb2d05e...` is fixed-display but still `decision=defer`, no `authorization_id`, no standing scoped auth, no probe/order authority. | Resume only on real candidate-scoped auth object, valid exact typed confirm matching the fixed template, or standing-auth delta that passes repo gates. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills with fees/slippage, controls, execution realism, and repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe produces candidate-matched outcomes. |
| `P1-FEE-TIER-MAKER-RATIO-EVIDENCE-DESIGN-NO-ORDER` | 1 | DEFERRED | PM -> QC/MIT -> E3/BB if private fee read is requested -> PM | Source-only design for fee-tier/maker-ratio evidence that can later attach actual fees and maker/taker labels to candidate-matched fills; no order/probe authority. | v582 aggressive hypothesis: actual fee tier and maker ratio could materially change AVAX after-cost edge. | Use only if P0 auth remains blocked and no real authorization delta appears; keep source/design-only unless E3/BB opens a private read envelope. |

## §2 Closed Markers To Prevent Rework

| ID | Status | Latest report | No-repeat rule |
|---|---|---|---|
| `P1-RUNTIME-HEALTH-HYGIENE-AUTH-TYPED-CONFIRM-GUARD-RUNTIME-SYNC-APPLY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--auth_typed_confirm_guard_runtime_sync_apply.md` | No-op already done: runtime source is `b224c759`; expected-head pins old/target are `0/11`; natural artifact confirms fixed typed-confirm display. |
| `P1-RUNTIME-HEALTH-HYGIENE-AUTH-TYPED-CONFIRM-GUARD-RUNTIME-SYNC-REVIEW` | DONE_WITH_CONCERNS_NO_APPLY | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--auth_typed_confirm_guard_runtime_sync_review_no_apply.md` | Superseded by v582 apply. Do not repeat read-only review. |
| `P0-BOUNDED-PROBE-AUTHORIZATION-TYPED-CONFIRM-GUARD` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--auth_typed_confirm_guard_source_fix.md` | Do not repeat source fix unless a post-sync bounded auth packet again exposes an exact typed-confirm phrase while preflight is not ready or authorization fields are incomplete. |
| `P1-RUNTIME-HEALTH-HYGIENE-SOURCE-SYNC-APPLY-GONOGO-NO-APPLY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--runtime_source_sync_apply_gonogo_no_apply.md` | Superseded only by v581/v582 auth-helper runtime delta. Do not reopen for docs/reports/TODO/worklog/changelog/SCRIPT_INDEX drift alone. |
| `P1-RUNTIME-HEALTH-HYGIENE-API-PROCESS-OWNERSHIP` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--api_process_ownership_readonly.md` | No-op unless `systemctl --user` unit state, API/watchdog PID ownership, service file, or runtime process cgroup changes. |
| `P1-AGGRESSIVE-ALPHA-MAKER-COST-CUSHION-WORKSHEET-NO-ORDER` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--maker_cost_cushion_worksheet_no_order.md` | Do not repeat unless fee assumptions, preview spread, candidate edge, or scoped auth evidence changes. |
| `P0-PROFIT-EVIDENCE-QUALITY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md` | Reopen only on new exchange inventory, fill attribution, or proof-quality evidence. |
| `P0-PROFIT-CANDIDATE-SELECTION` | DONE_WITH_CONCERNS | AVAX Sell candidate selected; v574 construction preview ready no order. | Reopen only if fresh evidence invalidates AVAX cap feasibility or ranking. |
| `P1-LEARNING-LOOP-CLOSURE` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--learning_ssot_decision_packet.md` | No-op already done: artifact `probe_ledger.jsonl` is current SSOT; PG-backed cutover is not current. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--autonomous_parameter_proposal_contract.md` | No-op already done: learning output becomes inactive review packet only, never direct order/risk/live mutation. |
| `P1-AGGRESSIVE-ALPHA-CANDIDATE-SOURCE-FRESHNESS-ALIGNMENT-NO-CAPTURE` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--candidate_source_freshness_alignment_atomic_preview_runner.md` | Do not repeat source alignment or public quote runner without new source/runtime/artifact delta and E3/BB review for exchange-facing work. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Profit priority | Optimize real risk-adjusted net PnL after fees/slippage only inside survival, Guardian/risk, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| Authorization | A changed defer artifact is not bounded-probe/order authority. Candidate-scoped bounded Demo grant requires a valid structured auth object or valid exact typed confirm after fixed runtime/preflight readiness plus E3/BB review. |
| Runtime/order path | Private/trading Bybit calls, order submit/cancel/modify, PG write, adapter/writer enablement, plan mutation, crontab/env edit, and service restart require reviewed runtime chain. |
| Cost Gate | Do not lower global Cost Gate or freshness gate. Proof must be candidate-matched and include actual fills, fees, slippage, lineage, controls, and execution realism. |
| Quote/adapter/preview/worksheet | Public quote, adapter snapshot, no-order construction preview, shadow placement, and cost-cushion worksheet are evidence-only, not order admission or profit proof. |
| Live/mainnet | Out of scope; no live/mainnet authority. |

## §4 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
git -C /Users/ncyu/Projects/TradeBot/srv rev-parse HEAD
sed -n '1,180p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--auth_typed_confirm_guard_runtime_sync_apply.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T122938Z_auth_typed_confirm_guard_runtime_sync_apply.json
ssh trade-core 'git -C /home/ncyu/BybitOpenClaw/srv rev-parse HEAD && git -C /home/ncyu/BybitOpenClaw/srv status --short'
ssh trade-core 'crontab -l | wc -l; crontab -l | grep -o dd22810ee41c353c1d214d9a3217862d7b2bac74 | wc -l; crontab -l | grep -o b224c759200d8dfc6fc4a53cbee39b8fb3683118 | wc -l'
ssh trade-core 'python3 - <<'"'"'PY'"'"'
import json
p="/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json"
with open(p) as f:
    d=json.load(f)
print(d.get("status"), d.get("decision"), d.get("candidate"), d.get("authorization_id"), d.get("probe_authority_granted"), d.get("order_authority_granted"), d.get("typed_confirm_expected"), d.get("typed_confirm_template"), d.get("typed_confirm_readiness"))
PY'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: The next PM can identify the next action in under one minute: P0 authorization is still blocked by missing machine-checkable scoped authorization; if no real auth delta appears, the next source-only aggressive blocker is fee-tier/maker-ratio evidence design.
