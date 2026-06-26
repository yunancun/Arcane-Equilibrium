# 玄衡 TODO — Active Dispatch Queue

**版本** v527 ｜ **日期** 2026-06-26
**Source pointer**：v527 is a docs-only checkpoint on source-code head `c6fabd96724b7a0249128a6f618cf332129bf906`; Linux runtime checkout remains `e0c2a0e17c8d00883c935d1ceb6897ccd9b9e36c` from the 2026-06-25T23:34Z read-only snapshot.
**Current mainline**：AVAX runtime/admission E3/BB review closed as no-authority `DONE_WITH_CONCERNS`; next checkpoint is runtime source-sync + post-restart reconciliation + adapter-enablement review, paused until operator resumes.
**Evidence links**：latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--avax_runtime_admission_e3_bb_review_todo_hygiene.md`; prior source-readiness report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--avax_authority_path_readiness_source_scan.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Runtime Snapshot

| Area | Timestamped fact | Next executable action |
|---|---|---|
| Source/runtime drift | 2026-06-25T23:34Z read-only snapshot: Mac source was ahead; Linux runtime checkout/crons were `e0c2a0e1`. TODO v527 changed docs only and did not touch runtime. | On resume, open the exact runtime review checkpoint before any sync, restart, crontab/env mutation, adapter enablement, PG write, or Bybit call. |
| AVAX source readiness | 2026-06-26T00:14Z source/test report: AVAX authority scanner returns `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`, missing seams `[]`, authority fields false. | Do not rerun source-readiness unless source seams, placement input, or scanner logic changes. |
| AVAX runtime/admission review | 2026-06-26 PM -> E3 -> BB review: PASS/DONE_WITH_CONCERNS for moving only to a separate runtime source-sync/reconciliation/adapter-enablement review. | Current review grants no runtime mutation, no adapter enablement, no probe/order authority, and no Bybit private/order endpoint use. |
| Remaining runtime blockers | 2026-06-26 helper print-json still reports `runtime_source_sync_not_verified`, `post_restart_pending_order_reconciliation_not_proven`, `runtime_adapter_enablement_not_performed_source_only_packet`. | Next checkpoint must address these blockers explicitly and separately. |
| Latest learning chain | 2026-06-25T22:29Z false-negative packet latest has AVAX rank 2, but runtime `_latest` proposal/preflight still select ETH Buy. | Use explicit candidate-scoped AVAX inputs; do not rely on `_latest` for AVAX proof. |

## §1 Selected P0 Dispatch Queue

| ID | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---|---|---|---|---|
| `P0-BOUNDED-PROBE-AVAX-RUNTIME-ADMISSION-E3-BB-REVIEW-DEMO-ONLY` | DONE_WITH_CONCERNS | PM -> E3 -> BB -> PM | Review may only decide whether to open the next runtime checkpoint. It must not mutate runtime, submit/cancel/modify orders, write PG, enable adapter/writer, or grant probe/order/live authority. | Report `2026-06-26--avax_runtime_admission_e3_bb_review_todo_hygiene.md`; E3 PASS/DONE_WITH_CONCERNS; BB PASS/DONE_WITH_CONCERNS; local readiness print-json confirms all authority fields false. | No-repeat. Do not rerun without source HEAD, runtime snapshot, PG snapshot, artifact mtime, or authorization delta. |
| `P0-BOUNDED-PROBE-AVAX-RUNTIME-SOURCE-SYNC-POST-RESTART-RECONCILIATION-ADAPTER-ENABLEMENT-E3-BB-REVIEW-DEMO-ONLY` | WAITING | PM -> E3 -> BB -> PM | Decide, in a fresh checkpoint, whether a bounded runtime source sync, post-restart pending-order reconciliation proof, and Demo-only adapter-enablement review path is safe. It still cannot place/cancel/modify orders or grant probe/order/live authority unless a later exact order-envelope checkpoint approves it. | Created by v527 E3/BB review. Known blockers: runtime source sync not verified, post-restart pending-order reconciliation not proven, adapter enablement not performed. | Resume only when operator asks to continue. First action: create a new `session_loop_state`, then run PM -> E3 -> BB review for this exact blocker. |

### P0 Standing Tracks

| ID | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---|---|---|---|---|
| `P0-EDGE-1` | ACTIVE | PM -> QC/MIT/AI-E -> PM | Close only with >=3 alpha candidates satisfying net/cost/stat/execution gates, or another accepted P0 edge path. | Gate-B/alpha evidence remains non-promotable; AVAX is the current selected bounded-Demo candidate path. | Continue source-only candidate research only when it does not repeat the selected AVAX blocker. |
| `P0-LG-3` | ACTIVE | PM -> E2 -> E4 -> QA -> PM | Deploy/rebuild only after review chain and migration/checksum discipline; runtime proof required before closure. | Source integrated in commits `deb3f3af..0802d52b`; runtime remains undeployed. | Re-run review chain before any deploy/rebuild. |
| `P0-OPS` | ACTIVE | Operator + PM/E3/BB/E1 as needed | Restore drill, system-level units, live-auth update, replay manifest feeding, and close-maker max-pending evidence recorded. | Operator-gated tails remain; historical OPS rows in changelog. | Wait for named operator windows; no silent runtime mutation. |

### No-Repeat AVAX Ladder

Closed source/read-only AVAX ladder: fresh reroute refresh block -> candidate-specific reroute source -> candidate-scoped chain smoke -> touchability bootstrap source -> authority path readiness source -> runtime/admission E3/BB review.

Reports:

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-25--avax_fresh_reroute_chain_refresh_blocked_todo_hygiene.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-25--avax_candidate_scoped_reroute_source_patch.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-25--avax_candidate_scoped_chain_smoke.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-25--avax_touchability_bootstrap_source_patch.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--avax_authority_path_readiness_source_scan.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--avax_runtime_admission_e3_bb_review_todo_hygiene.md`

No-repeat rule: do not reopen any closed ladder item unless there is a concrete source HEAD, runtime snapshot, PG snapshot, artifact mtime, or operator-authorization delta.

## §2 Active P1/P2 Engineering Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P1-COST-GATE-SEALED-HORIZON-REVIEW` | 1 | ACTIVE | PM -> QC/MIT/BB -> PM | Sealed evidence becomes a bounded proposal only after operator review, production learning-lane proof, execution-realism review, and separate Rust-authority probe approval. | v500-series scorecard/preflight artifacts in changelog. | Build/review bounded proposal contract only; no probe/order authority. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | ACTIVE | PM -> PA/CC -> PM | Decide durable learning SSOT: artifact ledger vs PG-backed Cost Gate learning ledger. | Prior governance packets in changelog. | Source/doc decision only unless PG write is separately reviewed. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | ACTIVE | PM -> PA/E1 -> E2 -> E4 -> PM | Learned candidate may become a reviewable proposal; it must not mutate order/risk/live state. | `autonomous_parameter_proposal.py` supports explicit `--selected-side-cell-key`; AVAX has review-only first-attempt and source-readiness paths. | Revisit after the selected runtime review; no direct order/risk/live mutation. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | ACTIVE | PM -> E3 -> BB -> PM | Reconcile cron expected-head drift and clarify API process vs service ownership. | Linux runtime remains `e0c2a0e1`; local source ahead. | Do not sync/restart here; keep runtime work inside the selected E3/BB checkpoint. |
| `P1-L2-ADVISORY-MESH-TAILS` | 1 | ACTIVE | PM -> AI-E/E2/E4 -> PM | First non-empty material day, E2E true distillation/model-call evidence, or B3 shadow runtime evidence. | Reports `2026-06-13--l2_v140_pipeline_activation.md`, `--l2_embedding_backfill_activation.md`, `--l2_b3_recall_wiring.md`. | Run only on new material/shadow evidence. |
| `AEG-S3-CANDIDATE-DIRECT-ROWS` | 1 | ACTIVE | PM -> QC/MIT/AI-E -> PM | Candidate rows satisfy regime, breadth, freshness, survivorship, execution-realism, DSR/PBO, and matched-sample gates. | Current discovery still not promotable. | On fresh Gate-B `ACTIONABLE_*`, run preflight first. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | ACTIVE | PM -> BB/E2/E4 -> PM | Full-scan pagination guard reviewed by BB/E2/E4 and production event proof recorded. | PM report `2026-06-19--reconciler_pagination_focused_review.md`. | Carry with LG-3/reconciler batch review. |
| `P3-110017-D2-AUDIT-REMOVED-SEMANTICS` | 3 | ACTIVE | PM -> E2/E4/QA -> PM | Formal E2/E4 closure plus production `reconcile_ghost_converge` event proof. | 2026-06-19 read-only DB had 0 production events. | Recheck only after real event or reconciler batch review. |
| `P1-A1A2-STAGE0R-RUNNER-IMPL` | 2 | ACTIVE | PM -> QC/MIT/E4/QA -> PM | Full CI/Linux E4/QC-MIT-QA signoff and trusted packet evidence. | Stage0R wrapper reports in changelog. | Continue only if Stage0R candidate/gate evidence changes. |
| `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` | 2 | WAITING | Operator + PM -> E3/BB -> PM | OP-1/2/3, review/deploy/restart, and first real stake evidence. | PM report `2026-06-19--earn_first_stake_capability_routing_focused_review.md`. | Wait for OP-1 key update and Earn variant/stake decision. |

## §3 Operator Actions And Passive Waits

| Action | Trigger / evidence | Impact / next step |
|---|---|---|
| Resume AVAX runtime checkpoint | Operator resumes after this requested pause. | Create new `session_loop_state`; run PM -> E3 -> BB for `P0-BOUNDED-PROBE-AVAX-RUNTIME-SOURCE-SYNC-POST-RESTART-RECONCILIATION-ADAPTER-ENABLEMENT-E3-BB-REVIEW-DEMO-ONLY`. |
| AVAX bounded Demo construction | Only after runtime source sync, post-restart reconciliation, adapter-enablement review, fresh BBO, and a separate exchange-facing order-envelope approval. | May still be no-order preview first; no proof/order/live authority follows from v527. |
| S2 Gate-B 24h real capture | Fresh `[GATE-B-WATCH]` alert or latest artifact `ACTIONABLE_START_NOW` / `ACTIONABLE_SCHEDULE`. | Run `aeg_s3_gate_b_preflight.harness` first; full-chain command must be `operator_recommended=true`. |
| OP-1 Bybit mainnet key update | Operator availability. | Blocks Earn Wave C, live-auth update, OPS-2 dry-run, and endpoint-file correction. |
| OP-2/OP-3 Earn variant + first Flexible stake | After OP-1. | Establish first `learning.earn_movement_log` evidence. |
| Restore drill / system-level service units | Operator low-trading 4h window and sudo availability. | Closes OPS protection gaps beyond user-level watchdog. |

## §4 Safety Invariants And Proof Exclusions

- Profit is optimized only inside survival, Guardian/risk gates, Decision Lease, Rust authority, authorization gates, auditability, and reconstructability.
- Operator's broad Demo/API authorization does not override E3/BB runtime chain, Rust authority, Guardian/risk, Decision Lease, or candidate-matched proof requirements.
- Do not lower global Cost Gate, widen cap/freshness gates, or fake freshness by editing/copying stale artifacts.
- Unattributed fills never count toward promotion or bounded-probe proof.
- `flash_dip_buy` demo fills, Paper archive, artifact counts, source smoke, replay-only results, and single-window MM positives cannot prove profitability.
- Proof must be candidate-matched, reconstructable, fee/slippage-aware, and risk-adjusted net after costs.
- Learning output may become a reviewable proposal only; it must not directly mutate order/risk/live state.

## §5 Aggressive Alpha Expansion Backlog

| Hypothesis path | Why it might make money | Fastest safe test | Authority |
|---|---|---|---|
| Candidate-scoped AVAX first-attempt near-touch path | AVAX rank 2 still has 73.5511bps avg net and 48/48 positive outcomes; v527 E3/BB found no blocker to opening the runtime review checkpoint. | Resume with runtime source-sync/post-restart reconciliation/adapter-enablement E3/BB review; then no-order construction/order-envelope review only if gates are fresh. | Review-only now; no order/probe authority. |
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
