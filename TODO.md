# Xuanheng TODO - Active Dispatch Queue

**Version** v581 | **Date** 2026-06-26
**Source/runtime pointer**: source/origin `b224c759200d8dfc6fc4a53cbee39b8fb3683118`; runtime `trade-core` clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74` as of `2026-06-26T12:19:53Z`; runtime crontab expected-head pins old/new `11/0`.
**Current posture**: v581 closes the typed-confirm runtime-sync review as no-apply for this paused round. Future apply is justified only as an atomic source + all-11 expected-head sync; P0 bounded authorization still has no admitted authority.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--auth_typed_confirm_guard_runtime_sync_review_no_apply.md`; latest Operator note `docs/CCAgentWorkSpace/Operator/2026-06-26--auth_typed_confirm_guard_runtime_sync_review_no_apply.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Facts That Affect Dispatch

| Fact | Value | Dispatch impact |
|---|---|---|
| Runtime source drift | `2026-06-26T12:19:53Z`: source/origin `b224c759200d8dfc6fc4a53cbee39b8fb3683118`; runtime `trade-core` source clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74`. | This drift now includes a cron-invoked auth review helper fix. Do not repeat read-only review; next movement is the exact apply blocker below or a real P0 auth delta. |
| Runtime expected-head pins | `2026-06-26T12:19:53Z`: crontab line count `70`; `dd22810ee41c353c1d214d9a3217862d7b2bac74` count `11`; `b224c759200d8dfc6fc4a53cbee39b8fb3683118` count `0`. | If sync is opened, source fast-forward and all 11 expected-head pin replacements must happen together. No partial pin edit. |
| Runtime services | `2026-06-26T12:19:53Z`: `openclaw-trading-api.service` user unit active/running MainPID `2218842`; `openclaw-watchdog.service` active/running MainPID `1538268`. | Future source/pin sync envelope must not restart services unless a separate deploy path explicitly authorizes it. |
| Bounded authorization artifact | Runtime latest auth sha `351bd18b233de35d972535248c0f8cc8f9b4cc49445765259acec4a97ce122d8`, mtime `2026-06-26T12:15:04.277174Z`; status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`; candidate `grid_trading|AVAXUSDT|Sell`; `decision=defer`; no `authorization_id`, no probe/order authority; stale runtime still emits exact `typed_confirm_expected='authorize_bounded_demo_probe:grid_trading|AVAXUSDT|Sell:0:'`. | This is not authorization. The exact phrase is stale/unsafe runtime output and must not be copied as proof or authority. v580 source fix suppresses it locally; runtime needs a later sync to emit the fixed behavior. |
| v581 E3 verdict | `E3(explorer)` returned `DONE_WITH_CONCERNS` / `GO_FUTURE_APPLY`: future runtime source sync plus all-11 expected-head replacement is justified for governance hygiene only. | Apply is not performed in v581 due operator-requested pause. Future apply still grants no probe/order/live authority and must not lower Cost Gate/freshness gates. |
| AVAX no-order evidence | Existing construction preview, cost-cushion worksheet, public quote/adapter path, and shadow placement data remain evidence-only. | They do not unlock P0 auth, order admission, Cost Gate proof, or promotion proof. Candidate-matched fills after scoped authorization are still required. |

## §1 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P1-RUNTIME-HEALTH-HYGIENE-AUTH-TYPED-CONFIRM-GUARD-RUNTIME-SYNC-APPLY` | 1 | DEFERRED | PM -> E3 -> PM | Runtime source clean at `b224c759200d8dfc6fc4a53cbee39b8fb3683118`; crontab line count preserved; expected-head old/new counts `0/11`; API/watchdog still active with unchanged MainPIDs unless separately authorized; next natural auth artifact no longer exposes exact typed-confirm while preflight/auth fields are incomplete. | v581 PM report + E3 verdict: future apply justified; no apply performed. | Resume only after operator asks to continue from the pause. Apply exact ff-only source sync plus all 11 expected-head replacements; no restart, cron run, PG write, Bybit call, order/probe/live authority, or Cost Gate change. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | PM -> E3 -> BB -> PM | Candidate-scoped bounded Demo authorization only; no global Cost Gate lowering; no live; no order/probe authority unless a valid scoped authorization is admitted and E3/BB review passes. | Latest runtime auth sha `351bd18b...` remains `decision=defer`, no admitted authority; exact typed-confirm phrase is stale runtime output, not valid authorization. | Resume only on real candidate-scoped auth object, valid exact typed confirm after fixed runtime/preflight readiness, or standing-auth delta that passes repo gates. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills with fees/slippage, controls, execution realism, and repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe produces candidate-matched outcomes. |

## §2 Closed Markers To Prevent Rework

| ID | Status | Latest report | No-repeat rule |
|---|---|---|---|
| `P1-RUNTIME-HEALTH-HYGIENE-AUTH-TYPED-CONFIRM-GUARD-RUNTIME-SYNC-REVIEW` | DONE_WITH_CONCERNS_NO_APPLY | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--auth_typed_confirm_guard_runtime_sync_review_no_apply.md` | Do not repeat read-only review. Next is exact apply or real P0 authorization delta. |
| `P0-BOUNDED-PROBE-AUTHORIZATION-TYPED-CONFIRM-GUARD` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--auth_typed_confirm_guard_source_fix.md` | Do not repeat source fix unless a bounded auth packet again exposes an exact typed-confirm phrase while preflight is not ready or authorization fields are incomplete after runtime is synced. |
| `P1-RUNTIME-HEALTH-HYGIENE-SOURCE-SYNC-APPLY-GONOGO-NO-APPLY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--runtime_source_sync_apply_gonogo_no_apply.md` | Superseded only by v581 auth-helper runtime delta. Do not reopen for docs/reports/TODO/worklog/changelog/SCRIPT_INDEX drift alone. |
| `P1-RUNTIME-HEALTH-HYGIENE-API-PROCESS-OWNERSHIP` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--api_process_ownership_readonly.md` | No-op unless `systemctl --user` unit state, API/watchdog PID ownership, service file, or runtime process cgroup changes. |
| `P1-AGGRESSIVE-ALPHA-MAKER-COST-CUSHION-WORKSHEET-NO-ORDER` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--maker_cost_cushion_worksheet_no_order.md` | Do not repeat unless fee assumptions, preview spread, candidate edge, or scoped auth evidence changes. |
| `P1-RUNTIME-HEALTH-HYGIENE-SOURCE-SYNC-REVIEW-NO-APPLY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--runtime_source_sync_review_no_apply.md` | Earlier no-apply review; v581 is the narrower auth-helper delta. |
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
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--auth_typed_confirm_guard_runtime_sync_review_no_apply.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T121621Z_auth_typed_confirm_guard_runtime_sync_review.json
ssh trade-core 'git -C /home/ncyu/BybitOpenClaw/srv rev-parse HEAD && git -C /home/ncyu/BybitOpenClaw/srv status --short'
ssh trade-core 'crontab -l | wc -l; crontab -l | grep -o dd22810ee41c353c1d214d9a3217862d7b2bac74 | wc -l; crontab -l | grep -o b224c759200d8dfc6fc4a53cbee39b8fb3683118 | wc -l'
ssh trade-core 'python3 - <<'"'"'PY'"'"'
import json
p="/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json"
with open(p) as f:
    d=json.load(f)
print(d.get("status"), d.get("decision"), d.get("candidate"), d.get("authorization_id"), d.get("probe_authority_granted"), d.get("order_authority_granted"), d.get("typed_confirm_expected"))
PY'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: The next PM can identify the next action in under one minute: pause now; when resumed, run the exact runtime source + expected-head apply blocker, unless a real scoped P0 authorization delta appears first.
