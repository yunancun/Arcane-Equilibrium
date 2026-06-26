# Xuanheng TODO - Active Dispatch Queue

**Version** v532 | **Date** 2026-06-26
**Source / runtime pointer**: Mac/origin `main` was verified clean at `1f13e8d25e612221e2afb5288c070d72cfe7ac79` before this docs checkpoint; Linux runtime remains clean at `d2cd70d092916194043e112eeb402fb92bacb699` with no source sync, rebuild, restart, crontab/env mutation, PG write, or Rust writer/adapter enablement.
**Current mainline**: Demo residual cleanup action is E3/BB-approved in principle, but blocked by control API CSRF invocation (`403 csrf_token_mismatch`, route did not execute); candidate selection remains blocked.
**Evidence links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_cleanup_action_csrf_block.md`; plan report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_exposure_cleanup_plan.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source / cron | 2026-06-26T01:50:28Z read-only check: Linux repo clean at `d2cd70d0`; crontab expected-head occurrences `d2cd70d0=11`, `1f13e8d2=0`; adapter flag count `0`; `OPENCLAW_ALLOW_MAINNET=1` count `0`. | No runtime sync/restart/rebuild was done. Runtime source updates remain separately reviewed. |
| Fresh pre-action Bybit demo inventory | 2026-06-26T01:58:16Z cursor-aware private GET-only inventory: `5` open orders on `ETCUSDT/FILUSDT/ICPUSDT/INJUSDT/NEARUSDT`, estimated open notional `486.24260000 USDT`; `3` nonzero positions on `FILUSDT/ICPUSDT/NEARUSDT`, value `435.14105000 USDT`, uPnL `-18.28692000 USDT`. Artifact on `trade-core`: `/tmp/openclaw/audit/bybit_demo_cleanup_action_pre_inventory/20260626T015816Z_pre_inventory.json`. | Scope still matches the approved cleanup target. This is inventory evidence only, not profit proof. |
| Cleanup action attempt | 2026-06-26T01:59:00Z: one control API POST attempt to `/api/v1/strategy/demo/session/stop` returned HTTP `403` with `csrf_token_mismatch` / missing `oc_csrf` cookie. Response artifact: `/tmp/openclaw/audit/demo_residual_cleanup_action/20260626T015900Z_session_stop_response.json`; meta: `/tmp/openclaw/audit/demo_residual_cleanup_action/20260626T015900Z_session_stop_meta.json`. | Route did not execute; no exchange mutation occurred. Do not retry under the same failed invocation envelope. |
| PG reconciliation | 2026-06-26 03:52:27+02 read-only PG: 72h demo fills `83`; missing `order_id=0`, missing `context_id=0`, unattributed/blank strategy `3`. 24h effective Working from `order_state_changes`: `2` linked PostOnly maker entries (`ETCUSDT`, `INJUSDT`). | Unattributed fills remain proof-excluded. Candidate selection stays blocked by exposure and lineage hygiene. |
| Passive healthcheck | 2026-06-26T01:50:53Z passive healthcheck `FAIL`; [68] demo `working_n=2`, resting about `487 USDT`, filled local exposure `0`, divergence `48735.0%`; [74] close-maker reject samples also `FAIL`. | No clean-book posture. Do not select/authorize a bounded Demo candidate yet. |

## §1 P0 Dispatch Queue

| ID | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY-BYBIT-DEMO-OPEN-ORDER-READ-ONLY-INVENTORY-E3-BB-REVIEW` | DONE_WITH_CONCERNS | PM -> E3 -> BB -> PM | Cursor-aware Bybit demo private GET inventory completed; proof exclusions explicit; no mutation or authority granted. | Report `2026-06-26--bybit_demo_open_order_read_only_inventory.md`; artifact `/tmp/openclaw/audit/bybit_demo_exchange_inventory/20260626T011756Z_inventory.json`. | No-repeat. Do not rerun without source/runtime/PG/artifact or authorization delta. |
| `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-PLAN-E3-BB-REVIEW` | DONE_WITH_CONCERNS | PM -> E3 -> BB -> PM | Residual exposure classified as 2 linked maker entries plus 3 residual positions protected by 3 reduce-only StopLoss conditionals. | Report `2026-06-26--demo_residual_exposure_cleanup_plan.md`; BB artifact `/tmp/openclaw/audit/bybit_demo_exchange_inventory_bb_review/20260626T014016Z_bb_inventory.json`. | No-repeat. Do not reclassify without evidence delta. |
| `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-ACTION-E3-BB-REVIEW` | BLOCKED_BY_RUNTIME_AUTHORIZATION | PM -> E3 -> BB -> PM | Execute exactly one demo-only position-aware cleanup only after authenticated CSRF delivery is verified; no live/mainnet, no direct Bybit POST shortcut, no PG write, no source sync/restart, no Cost Gate/probe/order/live authority. | Session state `/tmp/openclaw/session_loop_state_20260626T015300Z_demo_residual_exposure_cleanup_action.json`; E3/BB `DONE_WITH_CONCERNS`; fresh pre-inventory `20260626T015816Z`; blocked POST response `403 csrf_token_mismatch` at `20260626T015900Z`; report `2026-06-26--demo_residual_cleanup_action_csrf_block.md`. | Open a narrow runtime-auth/CSRF invocation checkpoint: prove a safe control API cookie delivery path without exchange mutation, then refresh E3/BB envelope before any second cleanup POST. |
| `P0-PROFIT-CANDIDATE-SELECTION` | BLOCKED | PM -> QC/MIT/BB -> PM | Select exactly one bounded Demo candidate only after clean-book posture or explicitly accepted residual risk; must use attributed, fee/slippage-aware evidence only. | Blocked by 5 demo open orders, 3 demo positions, healthcheck [68] FAIL, and 3 proof-excluded unattributed/blank-strategy fills. | Reopen only after cleanup action is DONE/DONE_WITH_CONCERNS with clean post-inventory or accepted residual posture. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | BLOCKED | PM -> E3 -> BB -> Operator/QC -> PM | Requires completed evidence-quality and candidate-selection blockers plus explicit bounded-probe packet. | No candidate selected; no authority granted. | No action. |
| `P0-PROFIT-OUTCOME-REVIEW` | WAITING | PM -> QC/MIT/BB -> PM | Review candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded probe outcomes exist. | Wait for authorized bounded probe outcomes. |

## §2 Active P1/P2 Engineering Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P1-RUNTIME-HEALTH-HYGIENE-API-CSRF-CLI-INVOKER` | 1 | ACTIVE | PM -> E3 -> PM | Provide a reviewed, secret-safe way to invoke CSRF-protected control API POSTs from CLI or confirm GUI/session path; must not touch exchange while proving cookie delivery. | Cleanup action blocked at HTTP `403` due missing `oc_csrf` cookie despite Bearer auth. | Source/read-only review of invocation path; no exchange-facing POST until refreshed E3/BB approval. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | ACTIVE | PM -> PA/CC -> PM | Decide durable learning SSOT: artifact ledger vs PG-backed Cost Gate learning ledger. | Current checkpoint did not change learning authority. | Source/doc decision only unless PG write is separately reviewed. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | ACTIVE | PM -> PA/E1 -> E2 -> E4 -> PM | Learned candidate may become a reviewable proposal; it must not mutate order/risk/live state. | Proposal helpers are review-only; no direct authority. | Revisit after P0 cleanup and candidate selection. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | ACTIVE | PM -> E3 -> BB -> PM | Reconcile runtime drift without unreviewed restart/rebuild/env mutation. | Linux checkout clean at `d2cd70d0`; healthcheck [68], [74], [82] still FAIL. | Feed cleanup/CSRF blocker into hygiene queue. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | ACTIVE | PM -> BB/E2/E4 -> PM | Full-scan pagination guard reviewed and production adoption path recorded. | Mac source has v530 full-scan helper; Linux runtime lacks it because no source sync. | Carry into runtime source-sync review only after P0 cleanup is resolved. |

## §3 Operator / Runtime Gates

| Gate | Trigger | Rule |
|---|---|---|
| Exchange cleanup | Any successful cancel/modify/close/order-affecting action for demo residual exposure. | Must use refreshed `PM -> E3 -> BB -> PM` envelope after the CSRF invocation blocker is resolved. No direct Bybit POST shortcut. |
| Runtime source sync | Deploying v530+ full-scan helper or CSRF invoker to Linux checkout. | Requires separate runtime/source-sync review; no service restart by default. |
| Bounded Demo probe | Candidate selected and clean-book posture accepted. | Requires explicit bounded-probe authorization; no live promotion. |
| Live/mainnet | Any mainnet key/order/path. | Not in scope; no live authority. |

## §4 Safety Invariants And Proof Exclusions

- Profit is optimized only inside survival, Guardian/risk gates, Decision Lease, Rust authority, authorization gates, auditability, and reconstructability.
- Do not lower global Cost Gate, widen caps/freshness gates, or fake freshness by editing/copying stale artifacts.
- Bybit inventory, healthcheck, source smoke, replay-only results, artifact counts, and single-window positives are not profitability proof.
- `flash_dip_buy` demo rows/fills, cleanup/risk-close rows, and unattributed fills cannot count toward bounded Cost Gate proof, bounded-probe proof, promotion, or risk-adjusted net PnL.
- Learning output may become a reviewable proposal only; it must not directly mutate order/risk/live state.

## §5 Aggressive Alpha Backlog

| Hypothesis path | Why it might make money | Fastest safe test | Authority |
|---|---|---|---|
| Clean-book unlock for one bounded candidate | Removing residual exposure and proof-excluded fills prevents contaminated PnL selection. | Resolve CSRF cleanup blocker, rerun post-clean inventory/health/PG read-only, then select exactly one candidate packet. | E3/BB for cleanup; no probe authority now. |
| CSRF-safe control-plane invoker | A reliable CLI/session invocation path shortens future demo-to-live-applicable risk-reduction loops without weakening auth. | Source/read-only review of cookie delivery; prove on non-exchange path or obtain refreshed E3/BB before exchange POST. | E3; BB only if exchange-facing. |
| Maker-path after exposure cleanup | Current linked PostOnly entries show passive placement still works, but edge is unusable until exposure is clean and fills are attributed. | Post-clean maker-ratio candidate packet with fee/slippage and adverse-selection controls. | Candidate review only; bounded probe later. |

## §6 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch && git rev-parse HEAD"
ssh trade-core "python3 -m json.tool /tmp/openclaw/audit/demo_residual_cleanup_action/20260626T015900Z_session_stop_response.json"
ssh trade-core "cd ~/BybitOpenClaw/srv && PGHOST=localhost PGUSER=trading_admin PGDATABASE=trading_ai bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
