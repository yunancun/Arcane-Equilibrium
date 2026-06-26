# 玄衡 TODO — Active Dispatch Queue

**版本** v530 ｜ **日期** 2026-06-26
**Source / runtime pointer**：Mac `main` is advancing this v530 source/docs checkpoint from `bd0a276d`; Linux runtime checkout remains clean at `d2cd70d092916194043e112eeb402fb92bacb699` and was not restarted/rebuilt/synced in this checkpoint.
**Current mainline**：Bybit demo open-order read-only inventory is done with concerns. Next blocker is a separate residual exposure cleanup/reconciler plan; candidate selection remains blocked until exchange exposure is clean or explicitly accepted by review.
**Evidence links**：latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--bybit_demo_open_order_read_only_inventory.md`; previous report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_resting_exposure_reconciliation_inventory.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source / cron | 2026-06-26T01:04Z read-only check: Linux repo clean at `d2cd70d0`; crontab expected-head occurrences `d2cd70d0=11`, current docs commit `bd0a276d=0`; adapter flag count `0`; `OPENCLAW_ALLOW_MAINNET=1` count `0`. | No runtime sync/restart/rebuild was done. Runtime source updates remain a separate reviewed action. |
| Bybit demo exchange truth | 2026-06-26T01:17Z cursor-aware private GET-only inventory: `5` exchange open orders, estimated open notional `400.97259600 USDT`; `2` linked PostOnly limit orders (`LINKUSDT`, `ARBUSDT`), `3` unlinked reduce-only conditional market orders (`NEARUSDT`, `FILUSDT`, `ICPUSDT`). Artifact: `/tmp/openclaw/audit/bybit_demo_exchange_inventory/20260626T011756Z_inventory.json` on `trade-core`. | Candidate selection stays blocked. Any cancel/modify/close/order-affecting action needs a separate E3/BB plan. |
| Demo positions | Same Bybit snapshot: `3` nonzero positions (`FILUSDT`, `ICPUSDT`, `NEARUSDT`), position value `435.14105000 USDT`, unrealised PnL `-21.44009000 USDT`. | Residual exposure must be classified before bounded demo candidate work. |
| PG reconciliation | 2026-06-26 read-only PG: 72h demo fills `79`; missing order/context/strategy attribution all `0`. 72h effective Working using `order_state_changes`: `2` exchange-linked, `27` stale `flash_dip_buy` not exchange-open, `2` stale zero-notional `risk_close` not exchange-open. | Root cause is not unattributed fills; it is residual exchange exposure plus stale local order-state semantics. |
| Healthcheck [68] | 2026-06-26 post-inventory passive healthcheck still FAIL: demo `working_n=5`, resting about `408 USDT` (`L401/S7`), divergence critical. | Do not treat inventory as clean-book proof. |

## §1 P0 Dispatch Queue

| ID | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY-BYBIT-DEMO-OPEN-ORDER-READ-ONLY-INVENTORY-E3-BB-REVIEW` | DONE_WITH_CONCERNS | PM -> E3 -> BB -> PM | Cursor-aware Bybit demo private GET inventory completed; PG/fill/healthcheck reconciliation recorded; proof exclusions explicit; no mutation or authority granted. | Report `2026-06-26--bybit_demo_open_order_read_only_inventory.md`; Bybit artifact `/tmp/openclaw/audit/bybit_demo_exchange_inventory/20260626T011756Z_inventory.json`; tests `61 + 5 passed`. | No-repeat. Do not rerun without source/runtime/PG/artifact or authorization delta. |
| `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-PLAN-E3-BB-REVIEW` | ACTIVE | PM -> E3 -> BB -> PM | Classify the `3` unlinked reduce-only conditional orders and `3` nonzero positions; decide source/read-only reconciler fix vs separately reviewed exchange cleanup. No cancel/modify/close/order action in this planning checkpoint. | Current exchange snapshot and healthcheck [68] FAIL from §0. | Start next round with `session_loop_state`; first safe work is source/read-only plan and E3/BB review packet. |
| `P0-PROFIT-CANDIDATE-SELECTION` | BLOCKED | PM -> QC/MIT/BB -> PM | Select exactly one bounded Demo candidate from false-negative / sealed horizon / MM current-fee / clean attributed demo fills only after exposure is clean or explicitly accepted. | Blocked by residual exchange exposure and healthcheck [68] FAIL. | Reopen after residual exposure blocker is DONE/DONE_WITH_CONCERNS with accepted risk posture. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | BLOCKED | PM -> E3 -> BB -> Operator -> PM | Requires completed evidence-quality and candidate-selection blockers plus explicit bounded probe approval. | No candidate selected; no authority granted. | No action. |
| `P0-PROFIT-OUTCOME-REVIEW` | WAITING | PM -> QC/MIT/BB -> PM | Review only candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded probe outcomes exist. | Wait for authorized bounded probe outcomes. |

## §2 Active P1/P2 Engineering Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P1-LEARNING-LOOP-CLOSURE` | 1 | ACTIVE | PM -> PA/CC -> PM | Decide durable learning SSOT: artifact ledger vs PG-backed Cost Gate learning ledger. | Prior governance packets in changelog; current checkpoint did not change learning authority. | Source/doc decision only unless PG write is separately reviewed. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | ACTIVE | PM -> PA/E1 -> E2 -> E4 -> PM | Learned candidate may become a reviewable proposal; it must not mutate order/risk/live state. | Existing proposal helpers are review-only; no direct authority. | Revisit after residual exposure cleanup and P0 candidate selection. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | ACTIVE | PM -> E3 -> BB -> PM | Reconcile health/runtime drift without unreviewed restart/rebuild/env mutation. | Linux checkout clean at `d2cd70d0`; healthcheck [68] still FAIL. | Feed residual exposure result into hygiene plan. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | ACTIVE | PM -> BB/E2/E4 -> PM | Full-scan pagination guard reviewed and production event proof recorded. | v530 added Bybit REST full-scan methods and focused tests locally; runtime source not synced. | Carry into reconciler/source-sync review if runtime adoption is needed. |
| `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` | 2 | WAITING | Operator + PM -> E3/BB -> PM | OP-1/2/3, review/deploy/restart, and first real stake evidence. | Still blocked by operator/key/runtime windows. | Wait for named operator window. |

## §3 Operator / Runtime Gates

| Gate | Trigger | Rule |
|---|---|---|
| Exchange cleanup | Any cancel/modify/close/order-affecting action for the 3 unlinked reduce-only conditionals or positions. | Must be a separate `PM -> E3 -> BB -> PM` plan. Current authorization does not bypass Guardian/risk/Decision Lease/Rust authority. |
| Runtime source sync | Deploying v530 full-scan helper to Linux checkout. | Requires reviewed runtime/source-sync action; no service restart by default. |
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
| Candidate-scoped maker re-entry after exposure cleanup | Current linked PostOnly orders prove the maker path can still place passive liquidity; clean book may unblock high-upside candidates. | Finish residual exposure plan, then select exactly one candidate from false-negative / MM / sealed-horizon evidence. | Research/proposal only now. |
| Reduce-only conditional hygiene | Removing exposure ambiguity can reduce false risk blocks and protect candidate evaluation from contaminated fills. | Source/read-only classify three unlinked conditionals against positions/fills/state changes. | E3/BB needed for any exchange mutation. |
| Regime-specific false-negative subset | Narrow regimes may clear fees even if broad strategy families are structurally sub-fee. | After clean exposure, build one candidate packet with matched controls and fee/slippage assumptions. | No order/probe authority until bounded-demo review. |

## §6 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "cd ~/BybitOpenClaw/srv && PGHOST=localhost PGUSER=trading_admin PGDATABASE=trading_ai bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
```

**Maintenance contract**：`TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
