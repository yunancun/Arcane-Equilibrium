# 玄衡 TODO — Active Dispatch Queue

**版本** v523 ｜ **日期** 2026-06-25
**Source pointer**：source includes the AVAX candidate-scoped reroute patch from this checkpoint; Linux runtime checkout remains `e0c2a0e17c8d00883c935d1ceb6897ccd9b9e36c` from the 2026-06-25T22:53Z read-only snapshot.
**Current mainline**：AVAX reroute review can now use a fresh cap-feasible selection wrapper instead of stale order-construction repair, but no fresh candidate-aligned runtime chain has been generated yet. Next active blocker is `P0-BOUNDED-PROBE-AVAX-CANDIDATE-SCOPED-CHAIN-SMOKE-DEMO-ONLY`.
**Evidence links**：latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-25--avax_candidate_scoped_reroute_source_patch.md`; prior block report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-25--avax_fresh_reroute_chain_refresh_blocked_todo_hygiene.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Runtime Snapshot

| Area | Timestamped fact | Next executable action |
|---|---|---|
| Source/runtime drift | 2026-06-25T22:53Z: Linux runtime checkout/crons still `e0c2a0e1`; v523 source patch is local/source-level until committed and separately synced. | Do not runtime-sync in this blocker. Treat runtime sync as a separate E3-reviewed action. |
| AVAX quote | 2026-06-25T22:38:40Z quote artifact `bbo_freshness_public_quote_capture_avax_sell_20260625T223840Z.json`, sha `fe36f2dd...`, status `PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER`, bid/ask `6.199/6.2`, BBO age `531.382ms`. | Quote is not construction/profit/probe proof. Do not spend another quote until reroute chain is fresh. |
| AVAX reroute inputs | 2026-06-25T22:57Z/23:00Z read-only evidence: fresh AVAX cap-feasible selection sha `909651b8...` and operator review sha `3e7cbb77...`; lower-price reroute latest sha `fcd7f925...` generated 2026-06-24T17:32Z and stale at ~29.4h. v523 source patch lets reroute consume the fresh selection wrapper. | Run a timestamped no-authority candidate-scoped chain smoke; do not overwrite `_latest` or widen 24h gates. |
| Latest learning chain | 2026-06-25T22:29Z false-negative packet latest has AVAX rank 2, but autonomous proposal/preflight latest select ETH Buy. | Source-only fix must support explicit candidate-scoped refresh without relying on `_latest` drift. |
| Touchability | 2026-06-25T22:30Z demo order-to-fill gap latest: `FILL_FLOW_PRESENT`, but `grid_trading\|AVAXUSDT\|Sell` has 0 candidate-reviewed orders; AVAX rows are flash/risk-close, not candidate-matched. | Placement repair will not become READY from current evidence; require candidate-matched touchability or explicit near-touch design contract. |

## §1 P0 Active Blockers

| ID | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---|---|---|---|---|
| `P0-BOUNDED-PROBE-AVAX-FRESH-REROUTE-CHAIN-REFRESH-DEMO-ONLY` | DONE | PM | Close this round only if no fake-refresh route is used and the exact blocker is recorded. | Closed with concerns in report `2026-06-25--avax_fresh_reroute_chain_refresh_blocked_todo_hygiene.md`: AVAX selection/operator-review are fresh; reroute is stale; latest chain drifted to ETH; AVAX candidate touchability is absent. | Do not rerun this blocker without new candidate-matched AVAX touchability, fresh AVAX-specific preflight/placement/readiness chain, or a source patch. |
| `P0-BOUNDED-PROBE-AVAX-CANDIDATE-SPECIFIC-REROUTE-CHAIN-SOURCE-ONLY` | DONE | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Reroute review accepts fresh cap-feasible selection wrapper as an alternate candidate source; stale/schema-invalid selection cannot borrow readiness from repair; downstream freshness/alignment/authority gates remain fail-closed. | Closed with concerns in PM report `2026-06-25--avax_candidate_scoped_reroute_source_patch.md`; focused `18 passed`, adjacent `179 passed`, py_compile and diff-check PASS. | Do not repeat source patch; move to timestamped no-authority chain smoke. |
| `P0-BOUNDED-PROBE-AVAX-CANDIDATE-SCOPED-CHAIN-SMOKE-DEMO-ONLY` | ACTIVE | PM -> E3 if Linux/runtime artifact generation is selected; otherwise PM local source/test/docs | Produce timestamped AVAX proposal/preflight/touchability/placement/readiness/reroute smoke outputs without `_latest` overwrite, PG write, Bybit call, or authority. Expected fail-closed output is acceptable if it identifies the next exact blocker. | v523 source patch removes stale repair packet as the blocker. Current evidence still lacks `grid_trading\|AVAXUSDT\|Sell` candidate-matched touchability. | Run local timestamped smoke from copied/read-only inputs or stop for E3 if using Linux runtime paths. |
| `P0-PROFIT-DEMO-LEARNING-LOOP` | ACTIVE | PM -> E3 -> BB -> PM for any public quote | Next construction proof must be candidate-matched, no-order, no-authority, and built from fresh reroute-review plus fresh BBO inside helper gates. | v521 quote READY; construction remains blocked until the AVAX candidate-scoped chain smoke is fresh. | Wait on the source-only reroute-chain fix before any new quote->adapter->preview chain. |
| `P0-EDGE-1` | ACTIVE | PM -> PA/QC/MIT/BB -> E1 after gate | Close only with >=3 alpha candidates satisfying net/cost/stat/execution gates, or another accepted P0 edge path. | Gate-B/alpha evidence remains non-promotable; see changelog. | Continue source-only candidate research or wait for fresh Gate-B actionable window. |
| `P0-LG-3` | ACTIVE | PM -> E2 -> E4 -> QA -> operator deploy gate | Deploy/rebuild only after review chain and migration/checksum discipline; runtime proof required before closure. | Source integrated in commits `deb3f3af..0802d52b`; runtime remains undeployed; historical runtime notes in changelog. | Re-run review chain before any deploy/rebuild. |
| `P0-OPS` | ACTIVE | Operator + PM/E1/MIT as needed | Restore drill, system-level units, live-auth update, replay manifest feeding, and close-maker max-pending evidence recorded. | Operator-gated tails remain; historical OPS rows in changelog. | Wait for named operator windows; no silent runtime mutation. |

## §2 Active P1/P2 Engineering Queue

| ID | P | Status | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|
| `P1-COST-GATE-SEALED-HORIZON-REVIEW` | 1 | ACTIVE | Sealed evidence becomes a bounded proposal only after operator review, production learning-lane proof, execution-realism review, and separate Rust-authority probe approval. | v500-series scorecard/preflight artifacts in changelog. | Build/review bounded proposal contract only; no probe/order authority. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | ACTIVE | Decide durable learning SSOT: artifact ledger vs PG-backed Cost Gate learning ledger. | Prior governance packets in changelog. | Source/doc decision only unless PG write is separately authorized and reviewed. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | ACTIVE | Learned candidate may become a reviewable proposal; it must not mutate order/risk/live state. | `autonomous_parameter_proposal.py` supports explicit `--selected-side-cell-key`; v522 needs candidate-scoped chain use. | Fold into AVAX source-only blocker if it reduces `_latest` drift. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | ACTIVE | Reconcile cron expected-head drift and clarify API process vs service ownership. | Linux runtime remains `e0c2a0e1`; local source ahead. | Do not sync/restart here; create E3-reviewed runtime action only when selected. |
| `P1-L2-ADVISORY-MESH-TAILS` | 1 | ACTIVE | First non-empty material day, E2E true distillation/model-call evidence, or B3 shadow runtime evidence. | Reports `2026-06-13--l2_v140_pipeline_activation.md`, `--l2_embedding_backfill_activation.md`, `--l2_b3_recall_wiring.md`. | Run only on new material/shadow evidence. |
| `AEG-S3-CANDIDATE-DIRECT-ROWS` | 1 | ACTIVE | Candidate rows satisfy regime, breadth, freshness, survivorship, execution-realism, DSR/PBO, and matched-sample gates. | Current discovery still not promotable. | On fresh Gate-B `ACTIONABLE_*`, run preflight first. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | ACTIVE | Full-scan pagination guard reviewed by BB/E2/E4 and production event proof recorded. | PM report `2026-06-19--reconciler_pagination_focused_review.md`. | Carry with LG-3/reconciler batch review. |
| `P3-110017-D2-AUDIT-REMOVED-SEMANTICS` | 3 | ACTIVE | Formal E2/E4 closure plus production `reconcile_ghost_converge` event proof. | 2026-06-19 read-only DB had 0 production events. | Recheck only after real event or reconciler batch review. |
| `P1-A1A2-STAGE0R-RUNNER-IMPL` | 2 | ACTIVE | Full CI/Linux E4/QC-MIT-QA signoff and trusted packet evidence. | Stage0R wrapper reports in changelog. | Continue only if Stage0R candidate/gate evidence changes. |
| `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` | 2 | WAITING | OP-1/2/3, review/deploy/restart, and first real stake evidence. | PM report `2026-06-19--earn_first_stake_capability_routing_focused_review.md`. | Wait for OP-1 key update and Earn variant/stake decision. |

## §3 Operator Actions And Passive Waits

| Action | Trigger / evidence | Impact / next step |
|---|---|---|
| AVAX bounded Demo construction | Fresh AVAX-specific reroute chain plus fresh E3/BB approval for any public quote. | May run no-order quote->adapter->preview; still no proof/order/live authority. |
| S2 Gate-B 24h real capture | Fresh `[GATE-B-WATCH]` alert or latest artifact `ACTIONABLE_START_NOW` / `ACTIONABLE_SCHEDULE`. | Run `aeg_s3_gate_b_preflight.harness` first; full-chain command must be `operator_recommended=true`. |
| OP-1 Bybit mainnet key update | Operator availability. | Blocks Earn Wave C, live-auth update, OPS-2 dry-run, and endpoint-file correction. |
| OP-2/OP-3 Earn variant + first Flexible stake | After OP-1. | Establish first `learning.earn_movement_log` evidence. |
| Restore drill / system-level service units | Operator low-trading 4h window and sudo availability. | Closes OPS protection gaps beyond user-level watchdog. |

## §4 Safety Invariants And Proof Exclusions

- Profit is optimized only inside survival, Guardian/risk gates, Decision Lease, Rust authority, authorization gates, auditability, and reconstructability.
- Do not lower global Cost Gate, widen cap/freshness gates, or fake freshness by editing/copying stale artifacts.
- Unattributed fills never count toward promotion or bounded-probe proof.
- `flash_dip_buy` demo fills, Paper archive, artifact counts, source smoke, replay-only results, and single-window MM positives cannot prove profitability.
- Proof must be candidate-matched, reconstructable, fee/slippage-aware, and risk-adjusted net after costs.
- Learning output may become a reviewable proposal only; it must not directly mutate order/risk/live state.

## §5 Aggressive Alpha Expansion Backlog

| Hypothesis path | Why it might make money | Fastest safe test | Authority |
|---|---|---|---|
| Candidate-scoped AVAX false-negative chain | AVAX rank 2 still has 73.5511bps avg net and 48/48 positive outcomes, while ETH is cap-blocked. | Source-only candidate-specific chain refresh; then one reviewed public quote->preview if fresh. | Source/test/docs only until quote step; quote needs E3/BB. |
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
