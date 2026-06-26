# Xuanheng TODO - Active Dispatch Queue

**Version** v585 | **Date** 2026-06-26
**Source/runtime pointer**: local/origin `main` was `51d45a0fd2746174e9e7977a9e36463eb9d8820c` before the v585 source/docs commit; final v585 commit is recorded in the PM response. Runtime `trade-core` remains clean at `b224c759200d8dfc6fc4a53cbee39b8fb3683118`.
**Current posture**: P0 bounded authorization is still blocked by missing machine-checkable scoped authorization. v585 closed review/hardening of the private fee-tier read envelope; no private read was performed.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--private_fee_tier_read_envelope_e3_bb_review_no_read.md`; latest Operator note `docs/CCAgentWorkSpace/Operator/2026-06-26--private_fee_tier_read_envelope_e3_bb_review_no_read.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Facts That Affect Dispatch

| Fact | Value | Dispatch impact |
|---|---|---|
| Operator pause | Prior operator pause was honored; the persistent goal resumed and v585 is a bounded review/hardening checkpoint. | Do not auto-advance into a real private read or P0 probe after v585. |
| Runtime source | Latest verified runtime source remains clean at `b224c759200d8dfc6fc4a53cbee39b8fb3683118`; crontab expected-head pins were already aligned in v582 (`0/11` old/target as of `2026-06-26T12:31:33Z`). | Do not repeat runtime sync for source-only research/docs drift. |
| Bounded authorization artifact | Natural runtime auth artifact sha `beb5a74d43907f98f9fa431a4b4bf1f8b4b25ebd661aa61ce9ff4380daf19039`, mtime `2026-06-26T13:30:53.436749Z`; status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`; candidate `grid_trading|AVAXUSDT|Sell`; `decision=defer`; no `authorization_id`, no probe/order authority; `typed_confirm_expected=None`; template `authorize_bounded_demo_probe:grid_trading|AVAXUSDT|Sell:<max_authorized_probe_orders<=3>:<authorization_id>`; readiness `PREFLIGHT_NOT_READY`. | New sha/mtime exists, but no admitted authorization delta. P0 remains blocked. Broad chat approval is not a runtime-scoped auth object. |
| Fee-tier/maker-ratio evidence design | Source-only smoke artifact `/tmp/openclaw/20260626T124030Z_fee_tier_maker_ratio_evidence_design_no_order/fee_tier_maker_ratio_evidence_design.json`, sha `ce17dffeb80a840d023b458580a87d37e4ba963b9dbcc2f8916904e682750375`, status `FEE_TIER_MAKER_RATIO_EVIDENCE_DESIGN_READY_NO_ORDER` for `grid_trading|AVAXUSDT|Sell`. | Future AVAX proof must attach actual fee-tier provenance, maker/taker labels, actual fees/slippage, and candidate-matched lineage. This is not order admission, Cost Gate proof, or profit proof. |
| Private fee-tier read envelope design | Source-only smoke artifact `/tmp/openclaw/20260626T130005Z_fee_tier_private_read_envelope_design_no_read/private_fee_tier_read_envelope_design.json`, sha `24180d6d04b11fdaa4163dc9f8dd0c916837ae0365ce9530afd54ab89eba7536`, status `PRIVATE_FEE_TIER_READ_ENVELOPE_READY_NO_READ` for `grid_trading|AVAXUSDT|Sell`. | Future fee-rate read envelope is defined, but no private read is authorized or performed. |
| Private fee-tier read envelope E3/BB review | Hardened source-only smoke artifact `/tmp/openclaw/20260626T133535Z_fee_tier_private_read_envelope_e3_bb_review_no_read/private_fee_tier_read_envelope_design_hardened.json`, sha `c1081ff412fd1e855b8a6ff4856734789e6c9e862ed8124330c48f87e77c165b`, status `PRIVATE_FEE_TIER_READ_ENVELOPE_READY_NO_READ` for `grid_trading|AVAXUSDT|Sell`. | Envelope is E3/BB-reviewed and hardened: `symbol=AVAXUSDT`, strict maker/taker parser, no cross-symbol persistence, standalone proof artifact only, no runtime cache replacement. Still no private read authorized or performed. |
| Verification | Focused private fee-tier envelope test `10 passed`; adjacent fee-tier evidence suite `29 passed`; `py_compile` passed; `git diff --check` passed; hardened smoke READY_NO_READ with all private-read/network/order/proof flags false; E3/BB `DONE_WITH_CONCERNS`; E2/E4 `DONE`. | v585 source hardening is locally verified. Actual private fee read remains a separate runtime/exchange-facing action. |

## §1 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | PM -> E3 -> BB -> PM | Candidate-scoped bounded Demo authorization only; no global Cost Gate lowering; no live; no order/probe authority unless a valid scoped authorization object or valid exact typed confirm is admitted and E3/BB review passes. | Latest runtime auth sha `beb5a74d...` remains `decision=defer`, no `authorization_id`, no standing scoped auth, no probe/order authority. | Resume only on a real candidate-scoped auth object, valid exact typed confirm matching the fixed template, or standing-auth delta that passes repo gates. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills with fees/slippage, controls, execution realism, and repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe produces candidate-matched outcomes. |
| `P1-FEE-TIER-PRIVATE-READ-RUNTIME-INVOKE-AUTHORIZATION` | 1 | BLOCKED | PM -> E3 -> BB -> PM | Any actual private fee-rate read requires a fresh one-shot runtime action: runtime host only, exact `AVAXUSDT`, no argv secrets, bounded timeout/no redirects, strict exact-row parser, sanitized artifact only, no PG write, no runtime fee-cache replacement, no Cost Gate/proof/authority use. | v585 envelope review is READY_NO_READ; no private read has been executed. | Stop unless a later checkpoint explicitly opens and authorizes the one-shot private read action. |

## §2 Closed Markers To Prevent Rework

| ID | Status | Latest report | No-repeat rule |
|---|---|---|---|
| `P1-FEE-TIER-MAKER-RATIO-EVIDENCE-DESIGN-NO-ORDER` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--fee_tier_maker_ratio_evidence_design_no_order.md` | No-op already done: helper, tests, SCRIPT_INDEX, smoke artifact sha `ce17dffe...`, and proof-exclusion contract exist. Reopen only if fee schema, maker policy, selected candidate identity, or auth packet contract changes. |
| `P1-FEE-TIER-PRIVATE-READ-ENVELOPE-E3-BB-REVIEW-NO-READ` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--private_fee_tier_read_envelope_e3_bb_review_no_read.md` | No-op already done: E3/BB review, source hardening, tests, SCRIPT_INDEX, smoke artifact sha `c1081ff4...`, and Operator note exist. Reopen only if Bybit endpoint policy, strict fee-proof requirements, candidate identity, or runtime read governance changes. |
| `P1-FEE-TIER-PRIVATE-READ-ENVELOPE-DESIGN-NO-READ` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--private_fee_tier_read_envelope_design_no_read.md` | No-op already done: source-only envelope helper, tests, SCRIPT_INDEX, smoke artifact sha `24180d6d...`, and E2/E3/BB review exist. Reopen only if Bybit fee-rate endpoint policy, fee-proof requirements, candidate identity, or private-read governance changes. |
| `P1-RUNTIME-HEALTH-HYGIENE-AUTH-TYPED-CONFIRM-GUARD-RUNTIME-SYNC-APPLY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--auth_typed_confirm_guard_runtime_sync_apply.md` | No-op already done: runtime source is `b224c759`; expected-head pins old/target are `0/11`; natural artifacts confirm fixed typed-confirm display. |
| `P1-RUNTIME-HEALTH-HYGIENE-AUTH-TYPED-CONFIRM-GUARD-RUNTIME-SYNC-REVIEW` | DONE_WITH_CONCERNS_NO_APPLY | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--auth_typed_confirm_guard_runtime_sync_review_no_apply.md` | Superseded by v582 apply. Do not repeat read-only review. |
| `P0-BOUNDED-PROBE-AUTHORIZATION-TYPED-CONFIRM-GUARD` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--auth_typed_confirm_guard_source_fix.md` | Do not repeat source fix unless a post-sync bounded auth packet again exposes an exact typed-confirm phrase while preflight is not ready or authorization fields are incomplete. |
| `P1-RUNTIME-HEALTH-HYGIENE-SOURCE-SYNC-APPLY-GONOGO-NO-APPLY` | DONE_WITH_CONCERNS | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--runtime_source_sync_apply_gonogo_no_apply.md` | Superseded only by runtime-affecting source deltas. Do not reopen for docs/reports/TODO/worklog/changelog/SCRIPT_INDEX drift alone. |
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
| Authorization | A changed defer artifact or broad chat approval is not bounded-probe/order authority. Candidate-scoped bounded Demo grant requires a valid structured auth object or valid exact typed confirm after fixed runtime/preflight readiness plus E3/BB review. |
| Runtime/order path | Private/trading Bybit calls, order submit/cancel/modify, PG write, adapter/writer enablement, plan mutation, crontab/env edit, and service restart require reviewed runtime chain. |
| Cost Gate | Do not lower global Cost Gate or freshness gate. Proof must be candidate-matched and include actual fills, fees, slippage, lineage, controls, and execution realism. |
| Quote/adapter/preview/worksheet/design | Public quote, adapter snapshot, no-order construction preview, shadow placement, cost-cushion worksheet, and fee-tier/maker-ratio design are evidence-only, not order admission or profit proof. |
| Live/mainnet | Out of scope; no live/mainnet authority. Demo evidence must be reconstructable and portable enough for later live review, but cannot bypass live gates. |

## §4 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
git -C /Users/ncyu/Projects/TradeBot/srv rev-parse HEAD
sed -n '1,180p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
sed -n '1,240p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--private_fee_tier_read_envelope_e3_bb_review_no_read.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T133535Z_fee_tier_private_read_envelope_e3_bb_review_no_read.json
python3 -m json.tool /tmp/openclaw/20260626T133535Z_fee_tier_private_read_envelope_e3_bb_review_no_read/private_fee_tier_read_envelope_design_hardened.json | sed -n '1,220p'
ssh trade-core 'git -C /home/ncyu/BybitOpenClaw/srv rev-parse HEAD && git -C /home/ncyu/BybitOpenClaw/srv status --short'
ssh trade-core 'python3 - <<'"'"'PY'"'"'
import json, hashlib, os, datetime
p="/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json"
b=open(p,"rb").read()
d=json.loads(b)
print(hashlib.sha256(b).hexdigest())
print(datetime.datetime.fromtimestamp(os.path.getmtime(p), datetime.timezone.utc).isoformat())
print(d.get("status"), d.get("decision"), d.get("candidate"), d.get("authorization_id"), d.get("probe_authority_granted"), d.get("order_authority_granted"), d.get("typed_confirm_expected"), d.get("typed_confirm_template"), d.get("typed_confirm_readiness"))
PY'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: The next PM can identify the next action in under one minute: P0 authorization is blocked without a machine-checkable auth delta; `P1-FEE-TIER-PRIVATE-READ-ENVELOPE-E3-BB-REVIEW-NO-READ` is already closed/no-repeat; absent P0 delta, the next private fee-tier step is an actual one-shot runtime read action and is blocked until explicitly opened as a separate PM -> E3 -> BB checkpoint.
