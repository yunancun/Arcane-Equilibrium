# Xuanheng TODO - Active Dispatch Queue

**Version** v577 | **Date** 2026-06-26
**Source/runtime pointer**: source checkpoint begins at `1e00a078305c7d222ed7f5428f9f5cd46ee91fa9`; runtime `trade-core` clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74` as of `2026-06-26T11:17:10Z`; no runtime/source/crontab/service apply in v577.
**Current posture**: v577 source-only maker cost-cushion worksheet is complete; P0 bounded authorization is still blocked; operator requested pause after this round.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--maker_cost_cushion_worksheet_no_order.md`; latest Operator note `docs/CCAgentWorkSpace/Operator/2026-06-26--maker_cost_cushion_worksheet_no_order.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Facts That Affect Dispatch

| Fact | Value | Dispatch impact |
|---|---|---|
| Runtime source/services | `2026-06-26T11:17:10Z`: runtime source clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74`; manual uvicorn process still visible at PID `2218842`; `systemctl` service ownership is not established in this snapshot. | v577 did not sync runtime, edit crontab, run cron, restart service, or change process ownership. API process vs service ownership remains a P1 hygiene clarification, not this checkpoint's blocker. |
| Runtime expected-head pins | `2026-06-26T11:17:10Z`: 11 active cron expected-head literals still pin `dd22810ee41c353c1d214d9a3217862d7b2bac74` (`5 EXPECTED_HEAD`, `1 OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD`, `5 OPENCLAW_EXPECTED_SOURCE_HEAD`). | Runtime and cron pins are internally consistent. If a future sync is opened, source fast-forward and all 11 expected-head pins must move in one reviewed checkpoint. |
| Bounded authorization | Runtime latest auth sha `bdaca35fb47ab874359703ee3e04e79c34bf9ed8b0d819d4f2c06e17986fa127`; status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`; AVAX candidate; `decision=defer`; no active authority admitted. | P0 bounded probe authorization remains blocked. Broad Demo API permission in chat is not treated as repo-valid order/probe authority. |
| AVAX no-order construction | Construction preview sha `f721bc3a...`; atomic summary sha `98c7d75...`; reroute sha `bc300277...`; preview is no-order only. | Evidence-only. Do not repeat quote/preview work without new E3/BB-reviewed evidence delta. |
| AVAX cost-cushion worksheet | `/tmp/openclaw/maker_cost_cushion_worksheet_20260626T111710Z/maker_cost_cushion_worksheet.json`, sha `074d2e1dc1a17a86cc5d88fa9e71aaf97d35b9a098af6e5d318e8b30111f9ab1`; status `MAKER_COST_CUSHION_WORKSHEET_READY_NO_ORDER`; maker stress margin `66.9239bps`, taker failure-analysis margin `59.9239bps` under explicit research assumptions. | Supports future operator review packet only. It is not order admission, Cost Gate proof, promotion proof, or current account fee proof. |

## §1 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | PM -> E3 -> BB -> PM | Candidate-scoped bounded Demo authorization only; no global Cost Gate lowering; no live; no order/probe authority unless a valid scoped authorization is admitted and E3/BB review passes. | Auth sha `bdaca35f...` remains `decision=defer`, no admitted authority. | Resume only on real candidate-scoped auth object, exact typed confirm, or standing-auth delta that passes repo gates. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills with fees/slippage, controls, execution realism, and repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe produces candidate-matched outcomes. |
| `P1-RUNTIME-HEALTH-HYGIENE-SOURCE-SYNC-APPLY-REVIEW` | 1 | DEFERRED | PM -> E3 -> PM | If opened, apply exact source sync envelope only: fast-forward runtime source and update all 11 expected-head pins together, then post-check clean head/pin counts/API process/auth unchanged. | E3 no-apply review found no blocker and no immediate need. | Do not run by default. Open only if operator/PM explicitly decides runtime needs newer source availability. |
| `P1-RUNTIME-HEALTH-HYGIENE-API-PROCESS-OWNERSHIP` | 1 | DEFERRED | PM -> E3 -> PM | Clarify manual uvicorn process vs service ownership without restart or process mutation. | `2026-06-26T11:17:10Z` snapshot found uvicorn PID `2218842` but no matching systemd unit listing. | Source/read-only review only if resumed and no P0 auth delta exists. |

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

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Profit priority | Optimize real risk-adjusted net PnL after fees/slippage only inside survival, Guardian/risk, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| Authorization | Broad Demo API permission is not bounded-probe/order authority. Candidate-scoped bounded Demo grant requires a valid structured auth object or exact typed confirm plus E3/BB review. |
| Runtime/order path | Private/trading Bybit calls, order submit/cancel/modify, PG write, adapter/writer enablement, plan mutation, crontab/env edit, and service restart require reviewed runtime chain. |
| Cost Gate | Do not lower global Cost Gate or freshness gate. Proof must be candidate-matched and include actual fills, fees, slippage, lineage, controls, and execution realism. |
| Quote/adapter/preview/worksheet | Public quote, adapter snapshot, no-order construction preview, and cost-cushion worksheet are evidence-only, not order admission or profit proof. |
| Live/mainnet | Out of scope; no live/mainnet authority. |

## §4 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
git -C /Users/ncyu/Projects/TradeBot/srv rev-parse HEAD
sed -n '1,180p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--maker_cost_cushion_worksheet_no_order.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T111710Z_maker_cost_cushion_worksheet_no_order.json
python3 -m json.tool /tmp/openclaw/maker_cost_cushion_worksheet_20260626T111710Z/maker_cost_cushion_worksheet.json
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && git rev-parse HEAD && git status --short'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: The next PM can identify the next action in under one minute: pause is intentional; P0 auth resumes only on real scoped auth delta; runtime sync apply is deferred and separate.
