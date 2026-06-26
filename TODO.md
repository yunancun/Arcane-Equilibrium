# 玄衡 TODO — Active Dispatch Queue

**版本** v529 ｜ **日期** 2026-06-26
**Runtime pointer**：Linux checkout remains clean at `d2cd70d092916194043e112eeb402fb92bacb699`; crontab expected-head occurrences are aligned (`d2cd70d0=11`, old `e0c2a0e1=0`); running engine was not rebuilt/restarted.
**Current mainline**：Demo resting-exposure read-only inventory is closed with concerns. Next active blocker is a separately reviewed Bybit demo private read-only open-order inventory; stop before cancel/modify/order action.
**Evidence links**：latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_resting_exposure_reconciliation_inventory.md`; prior runtime hygiene report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--avax_runtime_source_sync_cron_expected_head_sync.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Runtime Snapshot

| Area | Timestamped fact | Next executable action |
|---|---|---|
| Source / cron | 2026-06-26T00:57Z PM read-only check: Linux repo clean at `d2cd70d0`; crontab expected-head occurrences `d2cd70d0=11`, old `e0c2a0e1=0`; adapter flag count `0`; `OPENCLAW_ALLOW_MAINNET=1` count `0`. | Do not restart/rebuild or enable adapter until exchange-truth reconciliation is separately reviewed. |
| Demo PG working overhang | 2026-06-26T00:55Z direct read-only PG: 72h demo `Working` orders `30`; `29` are `flash_dip_buy` Limit/PostOnly Buy with `7264.930000 USDT` notional; `1` is `risk_close:phys_lock_gate4_giveback` Market Sell with zero notional/missing price. | Run a separately reviewed Bybit demo private read-only open-order inventory; PG alone is not exchange truth. |
| Healthcheck [68] | 2026-06-26T00:52:06Z passive healthcheck FAIL: 24h demo `working_n=6`, resting about `691 USDT` (`L684/S7`), divergence critical. | Treat count mismatch as window/semantic difference; do not rerun passive health as a substitute for exchange-truth inventory. |
| Fill / lineage quality | 2026-06-26T00:54Z read-only evidence: 72h demo fills `72`, unattributed order/context counts `0/0`; audit top-40 has `fill_rows=28`, `bbo_touched_no_fill_orders=6`, `no_bbo_coverage_orders=2`. | This is operational evidence only; not Cost Gate, bounded-probe, promotion, or PnL proof. |
| AVAX bounded-demo path | 2026-06-26 runtime hygiene is source-ready but exposure/reconciliation is not clean. | AVAX restart/adapter/order path remains blocked behind exposure reconciliation, fresh candidate inputs, and separate order-envelope review. |

## §1 Selected P0 Dispatch Queue

| ID | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESTING-EXPOSURE-RECONCILIATION-E3-BB-REVIEW` | DONE_WITH_CONCERNS | PM -> E3 -> BB -> PM | Read-only inventory/classification recorded; proof exclusions explicit; no Bybit/private/cancel/modify/order/PG-write/restart/adapter authority granted. | Report `2026-06-26--demo_resting_exposure_reconciliation_inventory.md`; E3 and BB both `DONE_WITH_CONCERNS`. | No-repeat. Do not rerun this read-only tranche without source/runtime/PG/artifact or authorization delta. |
| `P0-PROFIT-EVIDENCE-QUALITY-BYBIT-DEMO-OPEN-ORDER-READ-ONLY-INVENTORY-E3-BB-REVIEW` | ACTIVE | PM -> E3 -> BB -> PM | Separately approve and run only a Bybit demo private read-only open-order inventory; reconcile exchange-open orders against PG `Working`, fills, and healthcheck [68]. No cancel/modify/order action in this checkpoint. | 2026-06-26T00:55Z PG shows 30 demo `Working` rows; BB says PG alone is not exchange truth. | Create new `session_loop_state`; get exact E3/BB read-only endpoint review; run inventory only if approved; if cleanup is needed, stop and open a separate cancel/modify plan. |

### Standing P0 Tracks

| ID | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---|---|---|---|---|
| `P0-EDGE-1` | ACTIVE | PM -> QC/MIT/AI-E -> PM | Close only with >=3 alpha candidates satisfying net/cost/stat/execution gates, or another accepted P0 edge path. | Gate-B/alpha evidence remains non-promotable; AVAX is still only a selected bounded-Demo candidate path. | Continue source-only candidate research only when it does not bypass exposure reconciliation. |
| `P0-LG-3` | ACTIVE | PM -> E2 -> E4 -> QA -> PM | Deploy/rebuild only after review chain and migration/checksum discipline; runtime proof required before closure. | Source integrated in commits `deb3f3af..0802d52b`; runtime remains undeployed. | Re-run review chain before any deploy/rebuild. |
| `P0-OPS` | ACTIVE | Operator + PM/E3/BB/E1 as needed | Restore drill, system-level units, live-auth update, replay manifest feeding, and close-maker max-pending evidence recorded. | Operator-gated tails remain; historical OPS rows in changelog. | Wait for named operator windows; no silent runtime mutation. |

### Closed No-Repeat Markers

Closed AVAX ladder reports are linked here only to prevent repeat work, not as active queue items:

- `2026-06-25--avax_fresh_reroute_chain_refresh_blocked_todo_hygiene.md`
- `2026-06-25--avax_candidate_scoped_reroute_source_patch.md`
- `2026-06-25--avax_candidate_scoped_chain_smoke.md`
- `2026-06-25--avax_touchability_bootstrap_source_patch.md`
- `2026-06-26--avax_authority_path_readiness_source_scan.md`
- `2026-06-26--avax_runtime_admission_e3_bb_review_todo_hygiene.md`
- `2026-06-26--avax_runtime_source_sync_cron_expected_head_sync.md`

No-repeat rule: do not reopen closed ladder items unless there is a concrete source HEAD, runtime snapshot, PG snapshot, artifact mtime, or operator-authorization delta.

## §2 Active P1/P2 Engineering Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P1-COST-GATE-SEALED-HORIZON-REVIEW` | 1 | ACTIVE | PM -> QC/MIT/BB -> PM | Sealed evidence becomes a bounded proposal only after operator review, production learning-lane proof, execution-realism review, and separate Rust-authority probe approval. | v500-series scorecard/preflight artifacts in changelog. | Build/review bounded proposal contract only; no probe/order authority. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | ACTIVE | PM -> PA/CC -> PM | Decide durable learning SSOT: artifact ledger vs PG-backed Cost Gate learning ledger. | Prior governance packets in changelog. | Source/doc decision only unless PG write is separately reviewed. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | ACTIVE | PM -> PA/E1 -> E2 -> E4 -> PM | Learned candidate may become a reviewable proposal; it must not mutate order/risk/live state. | `autonomous_parameter_proposal.py` supports explicit `--selected-side-cell-key`; AVAX has review-only first-attempt/source-readiness paths. | Revisit after exposure/exchange-truth reconciliation; no direct order/risk/live mutation. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | ACTIVE | PM -> E3 -> BB -> PM | Reconcile runtime health drift without unreviewed restart/rebuild/env mutation. | Source checkout and cron expected-head pins are aligned at `d2cd70d0`; running engine was not rebuilt/restarted. | Remaining hygiene is health/reconciliation, not source drift. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | ACTIVE | PM -> BB/E2/E4 -> PM | Full-scan pagination guard reviewed by BB/E2/E4 and production event proof recorded. | PM report `2026-06-19--reconciler_pagination_focused_review.md`. | Carry with LG-3/reconciler batch review. |
| `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` | 2 | WAITING | Operator + PM -> E3/BB -> PM | OP-1/2/3, review/deploy/restart, and first real stake evidence. | PM report `2026-06-19--earn_first_stake_capability_routing_focused_review.md`. | Wait for OP-1 key update and Earn variant/stake decision. |

## §3 Operator Actions And Passive Waits

| Action | Trigger / evidence | Impact / next step |
|---|---|---|
| Bybit demo open-order read-only inventory | PG and healthcheck disagree on current demo working overhang; BB says PG alone is not exchange truth. | Next active checkpoint. Must be separately E3/BB-reviewed and read-only; no cancel/modify/order. |
| Cancel/modify cleanup plan | Only if the read-only Bybit inventory proves stale exchange-open orders that require cleanup. | Stop and create a separate E3/BB-reviewed plan before any exchange-affecting action. |
| AVAX bounded Demo construction | Only after exposure reconciliation, post-restart proof if required, adapter-enablement review, fresh BBO, and separate exchange-facing order-envelope approval. | May still be no-order preview first; no proof/order/live authority follows from v529. |
| OP-1 Bybit mainnet key update | Operator availability. | Blocks Earn Wave C, live-auth update, OPS-2 dry-run, and endpoint-file correction. |
| Restore drill / system-level service units | Operator low-trading 4h window and sudo availability. | Closes OPS protection gaps beyond user-level watchdog. |

## §4 Safety Invariants And Proof Exclusions

- Profit is optimized only inside survival, Guardian/risk gates, Decision Lease, Rust authority, authorization gates, auditability, and reconstructability.
- Operator's broad Demo/API authorization does not override E3/BB runtime chain, Rust authority, Guardian/risk, Decision Lease, or candidate-matched proof requirements.
- Do not lower global Cost Gate, widen cap/freshness gates, or fake freshness by editing/copying stale artifacts.
- Unattributed fills never count toward promotion or bounded-probe proof.
- `flash_dip_buy` demo rows/fills, cleanup/risk-close rows, Paper archive, artifact counts, source smoke, replay-only results, and single-window MM positives cannot prove profitability.
- Proof must be candidate-matched, reconstructable, fee/slippage-aware, and risk-adjusted net after costs.
- Learning output may become a reviewable proposal only; it must not directly mutate order/risk/live state.

## §5 Aggressive Alpha Expansion Backlog

| Hypothesis path | Why it might make money | Fastest safe test | Authority |
|---|---|---|---|
| Candidate-scoped AVAX first-attempt near-touch path | AVAX rank 2 still has strong false-negative net/cost evidence, but it lacks clean exchange/reconciliation proof. | Finish open-order truth inventory first, then no-order artifact refresh/order-envelope review only if gates are fresh. | Review-only now; no order/probe authority. |
| Maker/MM repeat-window filter | Current-fee-positive microstructure cells may survive fees via maker ratio and adverse-selection filters. | Wait for sample >=30 and independent repeat window; source-only scorecard hardening allowed. | No order/probe authority. |
| Regime-specific false-negative subset | Broad strategy families may be unprofitable while narrow regime/horizon subsets survive fees. | Build matched-control candidate rows and execution-realism filters from artifacts. | Research/source-only until proposal review. |

## §6 Deferred / Conditional Rows

| ID | Trigger |
|---|---|
| `P2-LIVE-AUTHZ-RUST-DIRECT-SOCKET-FUTURE` | Future architecture decision to move live authz context into Rust. |
| `P1-COST-GATE-DOUBLE-DEDUCT-TRIGGER` | Activate only if a positive cell or forward PnL proof is released. |
| `P2-AC19-ALT-BUCKET-FINAL-VERDICT-FOLLOWUP` | Reopen only if PA/QC/operator selects alpha/beta/C follow-up path. |
| `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` | Recheck on green Stage0R preflight, operator demo-canary approval, first real AEG-S3 candidate rows, residual flag-on first run, or high-funding A1 regime. |
| `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` | 2026-06-27 sample-size/retire-or-extend decision. |
| Sprint 4 first Live `$500` | W18-21 after P0-EDGE-1, LG-3, and OPS gates close. |

## §7 Handoff Rules

- Source/bug chain: `PM -> PA/E1 -> E2 -> E4 -> QA/PM`.
- Quant/data chain: `PM -> QC -> MIT -> AI-E -> PM`.
- Runtime/exchange/security chain: `PM -> E3 -> BB if exchange-facing -> PM`.
- Meta-doc updates: commit and push; keep Linux source sync as a separate reviewed runtime action.

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && PGHOST=localhost PGUSER=trading_admin PGDATABASE=trading_ai bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

**Maintenance contract**：`TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
