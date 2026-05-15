# 玄衡 TODO — Active Dispatch Queue

Version: v26
Date: 2026-05-15
Status: PM/PA/FA 5-day status audit sync. AMD-2026-05-15-01 canary rebase remains active: paper promotion evidence is frozen, A4-C D+12 paper-edge promotion is frozen, and Stage 1 demo micro-canary is blocked until a future green Stage 0R replay preflight. Step 5b Stage 0R remains GATE-RED (`eligible_for_demo_canary=false`) even after diagnostic producer restoration (`[57]` PASS; expected_dir distribution improved but edge/DSR still insufficient). A read-only OI-confirmed 5m feasibility probe also stayed red: runtime-style 5m breakout rows are sparse (`23` TA triple rows, `9` OI-confirmed rows) and OI-confirmed gross 15m was `-33.6345 bps`, so the packet remains non-promotional. `P1-HEALTHCHECK-55-INVARIANT` source-cleared `[55]` by replacing the `24/138` all-chain ratio heuristic with a fully-filled plan invariant (`25/25` fully-filled chains have real-fill ER; `0` missing; `13` partial chains surfaced separately). `P1-WA4B-INSERT-1` is DONE: feature baseline apply restored 646 active rows / 19 symbols and standalone `[67]` PASSes. Latest full passive healthcheck at `2026-05-15T15:47:01Z` is still **FAIL** due new `[27] intents_counter_freeze`: demo intent persistence stale 50.1m and live_demo stale 46.2m while approved verdicts/DCS continued; open `P1-INTENT-FREEZE-27`. `P1-INTENT-FREEZE-27` is now **DEPLOYED, POST-GRACE PENDING**: source/test fix for BTCUSDT exchange precision rounding was rebuilt on `trade-core` at runtime code line `7b33ab2e`; immediate direct `[27]` probe PASSed under fresh-restart grace (`demo 30min_n=16`, live_demo baseline pending after restart), and a later narrow probe at `2026-05-15T17:29:47Z` still PASSed under fresh-restart grace (`engine restarted 13.0m ago`), so close only after `[27]` passes outside grace. `V079` is no longer pending on `trade-core`: `_sqlx_migrations` shows version 90 max, versions 79/85/86/87/88/89/90 applied, and `learning.strategy_trial_ledger` contains 16,212 rows. The OI-confirmed 5m packet does not authorize replay eligibility, config changes, paper/demo launch, or canary promotion. Mac/origin/Linux source are synced at `e8944cf4`; runtime rebuild code line remains `7b33ab2e` because `e8944cf4` is docs-only. Rebuild completed with engine/API alive, but signed live authorization is absent and true-live remains blocked.

This file is the active work queue only. Historical closures, stale observation
tables, and superseded OpenClaw/Gateway assumptions are archived in
`docs/archive/2026-05-07--todo_v12_agent_openclaw_replan_archive.md` and
`docs/archive/2026-05-09--w_audit_verified_closed_archive_v3.md`.
v21 cleanup archive:
`docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`.
v24 stale-row audit archive:
`docs/archive/2026-05-15--todo_v24_stale_rows_archive.md`.
v26 alpha-path dispatch report:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--alpha_path_phase_c_dispatch.md`.

## §0.0 PM Freeze — 2026-05-15 Canary Rebase Guard

**Status**: ACTIVE PM freeze; AMD-2026-05-15-01 now carries the rebase authority.

- `W3 Stage 1 paper cohort` → **FROZEN**. Paper is permanently disabled for promotion evidence; `Environment::Paper × 7d` cannot be used as Stage 1 PASS evidence.
- `A4-C D+12 paper edge report` promotion path → **FROZEN**. A4-C promotion must be rebased to replay preflight + demo Stage 1 gate; legacy paper-edge report remains diagnostic/read-only only.
- Any plan, command, env file, script, or runtime launch that sets `OPENCLAW_ENABLE_PAPER=1` → **BLOCKED** unless a future operator decision explicitly reopens paper for non-promotion diagnostics.
- Step 2 update: AMD-2026-05-15-01 now revises W-AUDIT-9 / AMD-2026-05-09-03 to Stage 0R replay preflight + Stage 1 demo micro-canary.
- Step 3 update: **DONE 2026-05-15**. W-AUDIT-3b runtime smoke on `trade-core`: RouterLeaseGuard Drop Rust test PASS; ExecutorAgent fail-closed pytest PASS (`3 passed, 44 deselected`); `[55]` direct healthcheck confirms `chains_with_lease=89` (`chains=89`, `chains_with_idempotency=89`, `chains_with_report=89`).
- Step 3 A4-C update: **DONE 2026-05-15**. Spec v1.4 + W2 report CLI/tooling rebased to Stage 0R diagnostic output (`eligible_for_demo_canary=true/false`); legacy `promote_n2` compatibility field remains non-promotional and false after AMD-2026-05-15-01.
- Step 4 update: ✅ **SOURCE-CLEARED 2026-05-15 14:19 UTC**. `[55]` root cause was a healthcheck/filter bug: the old denominator used all complete decision chains, including no-fill and partial-fill chains, while Rust currently emits fill-completion ER only when `cum_filled_qty >= plan_qty * 0.999`. Patched check on current `trade-core` PG returns PASS with `chains=144`, `chains_with_real_fill_report=25`, `chains_with_plan_order_fill=38`, `chains_with_full_plan_fill=25`, `full_plan_fills_missing_report=0`, `partial_plan_fill_chains=13`, `bad_report_quality=0`, `bad_report_value_quality=0`.
- Step 5a update: **GATE-RED 2026-05-15**. Stage 0R rerun on `trade-core` at Linux repo head `eb181d70` using `sql/queries/w2_btc_alt_lead_lag_counterfactual.sql` fetched 4,417 rows over 7d. Mandatory metrics failed: pooled normal-signal `n=122`, `avg_net_bps=-3.5570`, `t=-1.5345`, `PSR(0)=0.0542`, `DSR(K=95)=0.0000`, block-bootstrap CI `[-3.9919, -1.2380]`, pooled R²(60/120/300)=`0.0004/0.0000/0.0017`, and no per-symbol `eligible_for_demo_canary=true`. Source-tier sanity: legacy `cross_asset_btc_lead_lag` panel rows=619; diagnostic source rows=12 snapshots / 84 expanded rows / 0 non-zero expected_dir at check time. No Stage 1 demo cohort selected. Evidence report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--stage0r_preflight_verification.md`.
- Step 5b update: **GATE-RED 2026-05-15 13:53 UTC**. After `OPENCLAW_ENABLE_BTC_LEAD_LAG_DIAGNOSTIC=1` restoration, `[57] btc_lead_lag_panel_health` PASSes (`age=27.2s`, `cohort=7/7`, `extreme=3.3%`, real book imbalance). Stage 0R fetched 5,740 rows over 7d and still returned `eligible_for_demo_canary=false`: pooled normal-signal `n=231`, `avg_net_bps=+0.3552`, `t=0.2231`, `PSR(0)=0.5877`, `DSR(K=95)=0.0000`, CI `[-1.0329, +2.1833]`, pooled R²(60/120/300)=`0.0009/0.0005/0.0027`. Expected_dir distribution improved but remains sparse: all-source NO_SIGNAL `95.63%` vs prior ~`97%`; diagnostic source `201` snapshots / `1,407` expanded rows / `121` non-zero expected_dir / `91.40%` NO_SIGNAL. No per-symbol `eligible_for_demo_canary=true`; `[55]` has since been source-cleared by P1-HEALTHCHECK-55-INVARIANT; `[58]` PASS as Stage 0 default. Evidence report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--stage0r_preflight_step5b.md`.
- Step 6 / OI-confirmed 5m packet: **SPEC + FEASIBILITY PROBE RED 2026-05-15**. `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--stage0r_oi_confirmed_5m_preflight.md` defines the `bb_breakout_oi_confirmed_5m` Stage 0R replay contract, row labels, OI freshness constraints, TA-only baseline comparison, and DSR/PBO/CI expectations. A later read-only feasibility probe found the data surface healthy (`panel.oi_delta_panel` 166,921 rows / 25 symbols, source `bybit_v5_ws_open_interest`; `market.klines` 5m 52,005 rows / 63 symbols) but the current runtime-style signal is underpowered and negative: 23 TA triple rows, 16 fresh-OI rows, 9 OI-confirmed rows, OI-confirmed gross 15m `-33.6345 bps`. Fixed diagnostic loosening still stayed underpowered/negative (best loose OI-confirmed n=23, gross 15m `-18.9629 bps`). This is not a full eligibility report, did not mutate runtime/code/config/DB/auth, and keeps `eligible_for_demo_canary=false`.
- Passive healthcheck update: **FAIL 2026-05-15 12:45 UTC**. Full unfiltered `trade-core` run at commit `7108035d` returned 67 checks = 55 PASS / 11 WARN / 1 FAIL. `[4] phys_lock_runtime` PASS (`exit_features` phys_lock 24h=1 / 7d=109) and `[Xb] pipeline_triangulation` PASS (close-fill-linked 15/15/15; `rejected_governance_raw` diagnostic-only), confirming the `7108035d` fixes. Only hard FAIL was `[67] feature_baseline_readiness` (`active feature_baselines=0`), which opened `P1-WA4B-INSERT-1`; the follow-up below closed it. Pre-fix WARNs needing attention were `[40]` negative realized edge, `[55]` partial real-fill propagation, `[59]` H0 acceptance quiet/missing live_demo snapshot, `[20]` H-state stub shape regression, `[45]` pricing source/age weakness. `[55]` has since been source-cleared by P1-HEALTHCHECK-55-INVARIANT; remaining WARNs are advisory/sample-maturity watches (`[41]`, `[42b]`, `[42c]`, `[48]`, `[51]`, `[11]`) plus non-[55] runtime warnings.
- P1-WA4B-INSERT-1 update: **DONE 2026-05-15 13:13 UTC / 15:13 Europe-Madrid**. Ran the canonical W-AUDIT-4b apply wrapper on `trade-core`: `OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw bash helper_scripts/cron/feature_baseline_writer_cron.sh`. Root cause was operational absence, not DDL: schema existed, source `trading.decision_context_snapshots` had 3,341,214 dry-run samples, but no cron entry/log and `observability.feature_baselines` had 0 active rows. Apply wrote 646 rows; active baselines now cover 19 symbols × 34 feature names. Standalone `[67] feature_baseline_readiness` PASSes with `active_rows=646 active_symbols=19 feature_names=34/34 online_latest_rows=43 vector_dim_min=34 vector_dim_max=34`. Drift events remain gated by configured burn-in.
- Latest healthcheck update: **FAIL 2026-05-15 15:47 UTC**. Full passive wait healthcheck no longer fails `[55]` or `[67]`, but hard-fails `[27] intents_counter_freeze`: demo stale=50.1m / live_demo stale=46.2m, 30min intents=0 while approved verdicts and DCS evaluations continued. Treat as runtime pipeline wedge (`trading_writer` intent INSERT / DCS evaluation path) and do not launch any demo canary until cleared.
- P1-INTENT-FREEZE-27 source update: **SOURCE/TEST CLOSED 2026-05-15, RUNTIME PENDING**. RCA on `trade-core` found the FAIL window was not a whole-writer outage: BTCUSDT approved risk verdicts were followed by exchange precision `qty=0 after rounding`, so the old exchange branch skipped order/intent after writing `Approved`. Source fix in `step_4_5_dispatch.rs` defers approved verdict persistence until `final_qty > 0`; if `final_qty <= 0`, it writes the explicit rejected qty=0 audit intent/verdict and negative decision feature. Targeted checks PASS: `python3 -m pytest helper_scripts/db/test_f7_new_healthchecks.py -q` (43 passed), `cargo test -q -p openclaw_engine tick_pipeline::tests::dual_rail_dispatch` (15 passed), `cargo test -q -p openclaw_engine tick_pipeline::tests::fast_track_reduce` (19 passed), and `rustfmt --check src/tick_pipeline/on_tick/step_4_5_dispatch.rs`. Full `cargo fmt --check` still reports unrelated pre-existing formatting drift outside the touched file. Do not mark runtime closed until deployed and `[27]` passes outside fresh-restart grace.
- P1-INTENT-FREEZE-27 deploy update: **DEPLOYED / POST-GRACE PENDING 2026-05-15**. Mac/origin/Linux synced at runtime code line `7b33ab2e` and `trade-core` ran `PATH=$HOME/.cargo/bin:$PATH bash helper_scripts/restart_all.sh --rebuild --keep-auth`. Release build completed; engine PID `4032406`, API PID `4032675`. Direct post-rebuild probes: `[27]` PASS under fresh-restart grace (`demo: stale=4.7m, 30min_n=16`; `live_demo` baseline pending after restart), `[66]` PASS, `[67]` PASS. Later narrow probe at `2026-05-15T17:29:47Z` still PASSed but was only 13.0m after restart, so keep `[27]` open until a post-grace check PASSes. `--keep-auth` warned signed live authorization is absent; no auth renewal was performed. Docs-only head `e8944cf4` is now synced across Mac/origin/Linux.
- Alpha-path dispatch update: **ACTIVE 2026-05-15**. A4-C remains revise/archive only; W-AUDIT-8a Phase C is split into C0 inventory / C1 revival. `market.liquidations` already exists from V002 but currently has 0 rows, and production WS subscriptions intentionally exclude old liquidation topics because they previously poisoned the connection. Do not subscribe `allLiquidation` or any liquidation topic in production until BB standalone proof passes. Current TODO IDs are canonical: `W-AUDIT-8b` = A4-A Funding Skew strategy, `W-AUDIT-8c` = A4-B Liquidation Cluster strategy; old execution-plan files named 8b/8c are R-2/R-3 aliases now marked as such.

---

## §0 Sprint Milestone Banner（FA 業務鏈視角，63% → 85-89%）

| Sprint | Week | 主題 | E1 capacity | Business chain milestone |
|---|---|---|---|---|
| **N+0** | W1-W2 | FOUNDATION HEAVY: W-AUDIT-9 + 8a Phase A + B 群 + C-A6 + 6 mid-ground | **5 active + 1 stand-by** (operator (a)) | 63→65% |
| **N+1** | W3-W4 | ALPHA SURFACE PANEL WIRING: 8a Phase B+C 並行 + 8d (BTC→Alt) + Stage 0R replay preflight + **Stage 1 demo micro-canary** prep | 4/6 | 65→70% must be recalculated after demo canary evidence |
| **N+2** | W5-W6 | 8d follow-up + 8a Phase D + Stage 2 demo cohort 14d（only after Stage 1 demo evidence） | **5 active + 1 stand-by** | 70→76% rebase pending |
| **N+3** | W7-W8 | 8c (Liquidation) IMPL + 8e (R-2) spec + Stage 3 demo full | 4/6 | 76→80% |
| **N+4** | W9-W10 | 8f (R-3) spec + 8b (Funding Skew) IMPL + 8e IMPL + Track W 收尾 | 4/6 | 80-83% |
| **N+5** | W11-W12 | 8f IMPL + 8g (R-4) spec + **first per-alpha-source supervised live** | **5 active + 1 stand-by** | **85-89%** |

**Stand-by E1 啟用條件**（operator 拍板 2026-05-09 (a)）：W-AUDIT-9 T3 stage-aware exception path 翻車 / W-AUDIT-8a Phase A byte-diff fail / W-AUDIT-6d mid-ground 與 8a Phase A 序列化 deadline 撞牆 / 任一 active E1 health incident → stand-by 即時補位。

**規劃帶 supervised live 概率**（FA）：6/15 樂觀 ~30% / 6/30 中位 ~40% / 7/15 悲觀 ~25% / 8/15 極悲觀 ~5%。

---

## §2 Architecture Boundary

- Formal product: `玄衡 · Arcane Equilibrium`.
- Bybit is the only exchange target.
- Rust `openclaw_engine` remains the trading, risk, strategy-config, and execution authority.
- Python/FastAPI is the control plane, bridge, GUI backend, replay/orchestration surface, and local 5-Agent runtime host. It is not the direct trading truth layer.
- The canonical GUI is the existing FastAPI console at `trade-core:8000/console`, now the OpenClaw Control Console.
- External OpenClaw Gateway is communication/mobile/supervisor/proposal relay only. It is not a trading conductor, not the local 5-Agent runtime, and not a second GUI.
- Local Scout / Strategist / Guardian / Analyst / Executor stay inside TradeBot. Cloud L2 calls must go through one supervisor escalation packet, explicit budget/model config, and durable `agent.ai_invocations` ledger reservation.
- Scanner is always-on infrastructure for market context, active-universe attribution, route fitness, opportunity evidence, and legacy would-block audit. It is not a trading authority and cannot hard-gate opens, closes, live auth, or order dispatch.
- `MessageBus` is legacy/advisory trace. Authoritative agent promotion requires typed lineage: StrategySignal -> StrategistDecision -> GuardianVerdict -> ExecutionPlan -> Decision Lease / idempotency -> ExecutionReport.
- Replay is advisory and diagnostic. Replay can fast-track preflight; it cannot substitute for runtime lineage or authorize live promotion.
- **Graduated Canary rebase**（AMD-2026-05-15-01 supersedes AMD-2026-05-09-03 Stage 1 paper semantics）：alpha-bearing pathway now uses Stage 0 shadow → **Stage 0R Replay Preflight** (`eligible_for_demo_canary=true/false`, not Stage 1 PASS) → **Stage 1 Demo micro-canary** (1 strategy × 1 symbol × `Environment::Demo` × 7d) → Stage 2 demo extended ×14d → Stage 3 demo full ×21d → Stage 4 LIVE_PENDING。DOC-08 §12 9 條安全不變量 / SM-04 ladder / Live boundary 5-gate / §二 16 原則硬不變式 4 範圍**仍強制 binary fail-closed**，不被 graduated canary 觸碰。

---

## §3 Latest State

### Current State (2026-05-15 PM/PA/FA audit)

- W-C MAG-082 Stage 2 **WINDOW_PASS 2026-05-11** and W-D MAG-083/MAG-084 **DONE 2026-05-11** are closed; proposal/mobile/Stage 3+/true-live gates remain separate and still blocked by edge/LG/ops prerequisites.
- A4-C BTC→Alt Lead-Lag Stage 0R remains **GATE-RED** after Step 5b (`eligible_for_demo_canary=false`). The OI-confirmed 5m packet is only a replay spec and does not change eligibility.
- `[55]` is source-cleared by `P1-HEALTHCHECK-55-INVARIANT`; `[67]` is restored to PASS after feature baseline apply; `[4]` phys lock and `[Xb]` triangulation are PASS after `7108035d`.
- V079 / `learning.strategy_trial_ledger` is runtime-applied on `trade-core` (migrations through V090 applied; 16,212 ledger rows observed). Old "V079 not applied / engine still 5/8 binary" text is archived in `docs/archive/2026-05-15--todo_v24_stale_rows_archive.md`.
- Remaining business root cause: 5 textbook strategies still lack durable positive net edge. `P0-EDGE-1`, `P0-LG-1/2/3`, `P0-OPS-1..4`, Alpha Surface Phase C/D, and alternative alpha candidates are the current path.

---

## §4 Active Dispatch Queue

**Dispatch Order** — ✅ MAG-082 runtime lineage PASS 2026-05-11；✅ MAG-083 三角 audit + MAG-084 sign-off CLOSED 2026-05-11；W-D wave closed。但 proposal relay / Telegram/WebChat / 第二 GUI / Stage 3/4 / true live autonomy 仍受 W-AUDIT-3..7 + LG-2/3/4 + edge net-positive + ops gates 限制，不因 W-D closure 自動解除。

**Status Legend**: ✅ DONE / ⏳ PENDING / 🟡 PARTIAL / 🔵 ACTIVE / ⛔ DEFER

### §4.1 Wave Roster (DUAL-TRACK + 8a-8h)

| Rank | Wave | Tag | Owner Chain | Status / Target | Exit Criteria |
|---:|---|---|---|---|---|
| 1 | `W-A` Executor fake-live runtime smoke | alpha-neutral | PM → E4 → PM | ✅ **DONE 2026-05-07** | P1-FAKE-1 path routes explicit live_demo metadata through real Rust IPC. |
| 2 | `W-B` Runtime decision-spine lineage wiring | alpha-neutral | PM → PA → E1 → E2 → E4 → PM | ✅ **DONE 2026-05-08** | Runtime shadow path writes nonzero typed decision objects/edges/idempotency. |
| 3 | `W-C` MAG-082 Stage 2 evidence window | alpha-neutral | PM → E3 → E4 → QA → PM | ✅ **WINDOW_PASS 2026-05-11** | Post Caveat 1+2 fix `ccf7a4bc` empirical SQL missed_n=0 entry / 14.7 state_changes/min；sign-off `docs/governance_dev/2026-05-11--w_c_window_pass_signoff.md`。 |
| 4 | `W-D` MAG-083 / MAG-084 | alpha-neutral | QA + PA + QC 三角 → operator | ✅ **DONE 2026-05-11** | MAG-083 triple-audit APPROVE (QA R-1/R-2/R-3 + PA 7 P1/3 P2 + QC S1-S4 caveats)；MAG-084 operator sign-off `docs/governance_dev/2026-05-11--w_d_mag084_signoff.md`。W-D wave CLOSED。 |
| 5 | `W-E` OpenClaw read-only observability | alpha-neutral | PM → PA → E1 → E2 → E4 → PM | ✅ **DONE 2026-05-07** | `/brief/latest` `/diagnostics` `/escalations` view models. |
| 6 | `W-F` Edge/data quality + Live Gate foundation | alpha-bearing | PM → QC/MIT/PA → E1/E4 → PM | ⏳ **PENDING** after W-A; before true-live | H0 production caller, pricing binding, supervised-live state machine. |
| 7 | `W-G` Proposal/approval/mobile relay | alpha-neutral | PM → CC/FA/PA → E1/E2/E4 → PM | 🟡 **BACKEND FOUNDATION DONE 2026-05-07**（待 mobile relay）| Gateway/console proposal/approval relay; no direct order/config/live-auth. |
| 8 | `W-AUDIT-1` Docs sync + governance compliance | alpha-neutral | TW + R4 + PM + PA | ✅ **DONE 2026-05-09** | CLAUDE.md §三/§五/§四 lease drift sync + AMD §5.4.1 + W-C auth file + docs/README + SPECIFICATION_REGISTER + ADR-0015..0019 + SCRIPT_INDEX + MIT/BB workspace READMEs. |
| 9 | `W-AUDIT-2` Security IMPL (4 HIGH) | alpha-neutral | E1×4 + E2 + E4 + E3 | ✅ **DONE 2026-05-09** | F-24/F-25 mutating routes gated; F-23 tailnet auto bind; F-03 lease writer; AI socket chmod 0600. Runtime deploy `862e79b7`: V078 applied, lease_transitions rows=103. |
| 10 | `W-AUDIT-3` ExecutorAgent fake-live | alpha-neutral | E1 + E1a + E2 + E4 + PA + PM | ✅ **SOURCE/SMOKE CLOSED** 2026-05-15; `[55]` source-cleared after P1 invariant fix | F-17 ✅ / F-15 ⚠️ / SM-05 Option A / F-01 source/test closed. **`W-AUDIT-3b` Sprint N+1 W4 RouterLeaseGuard Drop test 已 land** (commit `22efd9de`) and runtime smoke passed on `trade-core`: RouterLeaseGuard Drop Rust PASS + fail-closed pytest PASS + `[55] chains_with_lease=89`. P1-HEALTHCHECK-55-INVARIANT later proved 25/25 fully-filled chains have real-fill ER, so this is no longer an independent demo-canary blocker. |
| 11 | `W-AUDIT-4` ML 基座 + dead schema | alpha-bearing | E1×6 並行 + MIT + E2 + E4 | 🟡 **PARTIAL** → `W-AUDIT-4b` M1+M2+M3 ✅ DONE Sprint N+0 (commits `4a90966a` + `404174a4` + `e93a6e5c` + `a01d05ed`); `P1-WA4B-INSERT-1` ✅ DONE 2026-05-15; N+1+ scope corrected to 3 retained INSERT tables + 2 views + 1 dropped/no-DDL target | Corrected 4b scope: `feature_baselines` writer/schedule/healthcheck restored active rows (646 rows / 19 symbols / 34 feature names; `[67]` PASS), `cost_edge_advisor_log` row-growth confirmed, `drift_events` waits active baselines + configured burn-in; 2 companion views are read-only projections; `scorer_predictions` dropped/no-DDL。M3 producer chain integrity post-M3 100% ✅ (per 2026-05-10 PG empirical)。Decision-3 採納合併入 `W-AUDIT-8f` (R-3) Hypothesis Pipeline 同 wave 做。 |
| 12 | `W-AUDIT-5a/5b` 性能/結構/CI/跨平台 | alpha-neutral | E1×6 並行 + E5 + E2 + E4 | 🟡 **PARTIAL** since 2026-05-09; **5a/5b 主體 ✅ DONE N+1 W1** (commit `4a5e26ec` dead-code cleanup + runner split + REST dedup + warnings fix) | F-21 ✅ / F-27 ✅ / F-test-h-state ✅ / F-12 ✅ / F-26 CI matrix ✅ / W-AUDIT-5b event_consumer ✅; 剩 F-20 舊 worktree dump cleanup（`.claude/worktrees/` 3.6GB + `/private/tmp/` prunable worktrees）。 |
| 13 | `W-AUDIT-6` 策略 + 量化 promotion gate | alpha-bearing | E1×5 + QC + E2 + E4 + PM | 🟡 **SOURCE/TEST CLOSED 2026-05-09** + `W-AUDIT-6c` runtime apply + `W-AUDIT-6d` mid-ground Sprint N+0 + `W-AUDIT-6-3c` V086 ✅ DONE 2026-05-10 (production applied) | AMD-02 Option ii: grid CONDITIONAL ORDIUSDT, ma_crossover REVISE, bb_breakout 5m, funding_arb RETIRE (per ADR-0018), bb_reversion pair MA. W-AUDIT-6c VaR/CVaR/EVT IMPL `cc6476dd`. **`W-AUDIT-6d` mid-ground 保 6 / 砍 6** (見 §7)。**`W-AUDIT-6-3c` V086 reject_reason_code 12+14 enum** ✅ production deploy + writer code (commit `05e44ede`) — D+1 evening engine restart deploy producer。 |
| 14 | `W-AUDIT-7` AI 棧 + GUI/UX | alpha-neutral | E1×4 + AI-E + A3 + E2 + E4 + ops | 🔵 **ACTIVE** → `W-AUDIT-7c` Sprint N+2 | F-30 prompt modal / F-system-mode-confirm 5s countdown / F-strategist-cap 30→50 ADR-0022 ✅ land 2026-05-10 / F-28 ContextDistiller IMPL. 剩 F-07 ANTHROPIC_API_KEY + cea-env. Layer2 autonomous loop sunset by ADR-0020. |
| 15 | `W-AUDIT-8a` Alpha Surface Foundation (R-1 spec) | alpha-bearing | PA → E1 → E2 → E4 + MIT/QC/CC/BB → PM | ✅ **Phase A + Phase B DONE Sprint N+1 W1** (Phase A `c9fb0b8f`; Phase B panel_aggregator `0b76a4db` + `3d0ea347` + `ddf0cebe` + consumer wiring `7a07348b` + `31dba487`) / 🔵 **Phase C0 dispatch ACTIVE** / C1 revival + Phase D 待 BB/MIT gate | funding_curve aggregator (B-1) + oi_delta aggregator (B-2) + BB WS subscription (B-3) + bb_breakout real OiDeltaPanel consume fail-closed (B-4) 全 land。Phase C split: C0 inventory / no runtime topic mutation first；C1 re-enable liquidation writer/pulse only after BB standalone proof. Phase B WS-first design: 0 REST cost ongoing。 |
| 16 | `W-AUDIT-8b` A4-A Funding Skew Directional 新策略 | alpha-bearing | PA spec → E1 IMPL + QC + MIT + BB review | ⏳ **DEFER** Sprint N+3 spec → N+4 IMPL (1 sprint) | funding rate 期限結構 directional alpha；demo signal noise（mainnet 才能完整驗證）；25-symbol funding curve 消費 AlphaSurface Tier 2。 |
| 17 | `W-AUDIT-8c` A4-B Liquidation Cluster Reaction 新策略 | alpha-bearing | PA spec → E1 (Rust hot-path) + QC + BB review WS | ⏳ **DEFER** Sprint N+2 spec → N+3 IMPL (1.5 sprint) | Bybit `allLiquidation` WS topic 真接；event-trigger 模式；消費 AlphaSurface Tier 3 microstructure。 |
| 18 | `W-AUDIT-8d` A4-C BTC→Alt Lead-Lag 新策略 | alpha-bearing | PA spec → E1 IMPL + QC review | ✅ **DONE Sprint N+1 W1** (Spec v1.2+v1.3 D+0; IMPL `3d0ea347` btc_lead_lag producer + `58970d24` IPC slot + `31dba487` strategy consumers + `4b267dff` P0 stale fix + `1f0354cf` E2 review) / ✅ **v1.4 rebase DONE 2026-05-15** / **paper promotion FROZEN** / ❌ **Stage 0R Step 5b GATE-RED 2026-05-15** | BTC 1m ≥1.5σ lead signal; 7-alt cohort; grid_trading/ma_crossover shadow log; bb_reversion CrossAsset filter。Legacy D+12 paper-edge promotion path frozen; spec + W2 report CLI now emit Stage 0R diagnostic `eligible_for_demo_canary=true/false` only, with Stage 1 demo as sole promotion gate. Step 5b after diagnostic producer restoration improved expected_dir distribution (`[57]` PASS; all-source NO_SIGNAL `95.63%`, diagnostic source signal `8.60%`) but still returned `eligible_for_demo_canary=false` (`avg_net_bps=+0.3552`, `PSR(0)=0.5877`, `DSR=0.0000`, R² fail all symbols); no Stage 1 demo cohort selected. Spec: `docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md`. |
| 19 | `W-AUDIT-8e` (R-2) Strategist Alpha Source Orchestrator | alpha-bearing | PA spec → E1 IMPL | ⛔ **DEFER** Sprint N+4 spec → N+5 IMPL (2-3 sprint) | Strategist 從 4×5 hardcoded regime preferences → AlphaSourceRegistry + 動態 Sharpe-by-regime + Hypothesis sourcing。 |
| 20 | `W-AUDIT-8f` (R-3) Hypothesis Pipeline + W-AUDIT-4 ML 併入 | alpha-bearing | PA spec → E1 IMPL + MIT spec | ⛔ **DEFER** Sprint N+5 IMPL (2-3 sprint) | learning.hypotheses table state machine + Decision Lease + Hypothesis 關係 + W-AUDIT-4 6 dead schema 併入解 attribution_chain 0.5%→80% root cause（Decision-3 confirmed）。 |
| 21 | `W-AUDIT-8g` (R-4) Per-alpha-source Live Promotion Gate | alpha-bearing | PA spec → E1 IMPL | ⛔ **DEFER** Sprint N+7+ (2 sprint) | LiveBudget(alpha_source_id, slice) 替代「整 system live_reserved」線性 LG-2/3/4/5；FA defer 至 N+7（W-AUDIT-9 已部分覆蓋）。 |
| 22 | `W-AUDIT-8h` Alpha Sources GUI tab + Hypothesis Lab GUI tab | alpha-neutral | E1a + A3 review | ⛔ **DEFER** Sprint N+4-N+6 (1 sprint) | A3 建議 13→15 tab。 |
| 23 | `W-AUDIT-9` Graduated Canary Foundation IMPL | alpha-bearing | E1 (5 active + 1 stand-by 並行) | ✅ **T1-T7 DONE Sprint N+0 closure 2026-05-10** (HEAD `b6ed4975`)；W5-E1-A CANARY-STAGE-CRITERIA-1 ✅ DONE D+0 (commit `6529e37e` +2441 LOC) + V089 SQL seed deployed；W5-E1-C DYNAMIC-UNBLOCK ✅ DONE D+0 (commit `d17d7863` +1700 LOC) + V090 deployed；**Stage 1 paper cohort FROZEN 2026-05-15** | AMD-2026-05-15-01 rebases stage semantics: paper Stage 1 disabled; Stage 0R replay preflight + Stage 1 demo micro-canary gate replace old paper entry path. |
| 24 | `W-AUDIT-10` (R-5) Spec-as-Code + Module Lifecycle SM | alpha-neutral | PA spec → E1 IMPL | ⛔ **DEFER** 中期 (1-2 sprint) | CI gate spec drift > 7d auto-fail + module/table lifecycle header + 自動抽 SCRIPT_INDEX/SPEC_REGISTER。 |

### §4.1.1 Completed Sprint Ledgers Archived

Sprint N+0, Sprint N+1 D+0, Phase 3, Phase 4 W1+W2 execution statistics are
closed and archived in
`docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`. Active
follow-ups remain in §10 / §11 / §12.

### §4.2 Cross-Wave Conflict Resolution（4 條，PA §3.3 必繼承）

| # | 衝突 | Files / Surface | 解 |
|---|---|---|---|
| 1 | W-AUDIT-8a Phase A migration ↔ W-AUDIT-6d mid-ground 5 策略改動 | `bb_breakout/mod.rs` / `ma_crossover/strategy_impl.rs` / `bb_reversion/mod.rs` | **序列化**：先 6d mid-ground，再 8a Phase A |
| 2 | W-AUDIT-9 T3 shadow_mode_provider stage-aware ↔ ExecutorAgent shadow_mode 接線 | `executor_config_cache.py` / `executor_agent.py` | **W-AUDIT-3b 必先 land**；T3 結束前 ExecutorAgent shadow=true 不動 |
| 3 | W-AUDIT-8a Phase B+C ↔ W-AUDIT-5b 性能 wave | `tick_pipeline/mod.rs` | Phase B+C 並行於 N+1，5b 性能 catch-up reserved slot |
| 4 | A 群 3 新策略（8b/8c/8d）↔ W-AUDIT-9 Stage 1 cohort 選擇 | governance/canary | **FROZEN 2026-05-15**: A4-C 不再用 Stage 1 paper cohort 入場；改走 Stage 0R replay preflight + demo Stage 1 gate（AMD-2026-05-15-01）。 |
| 5 | TODO `W-AUDIT-8b/8c` ↔ legacy execution_plan `8b/8c` 檔名 | docs/execution_plan | **TODO IDs 為 SoT 2026-05-15**: `8b`=A4-A Funding Skew，`8c`=A4-B Liquidation Cluster；舊 `w_audit_8b_strategist...` / `w_audit_8c_hypothesis...` 是 R-2/R-3 alias（現 tracked as `8e/8f`），不得拿來當策略 spec。 |

---

## §5 Active Sign-off Delta

Full Sprint N+0 22-invariant ledger is closed and archived in
`docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`.

Current sign-off deltas only:
- ❌ **Stage 0R GATE-RED 2026-05-15**: A4-C Step 5b returned
  `eligible_for_demo_canary=false` after diagnostic producer restoration; no
  Stage 1 demo cohort selected.
- 🟡 **OI-confirmed 5m Stage 0R packet remains non-promotional**: the packet
  defines `bb_breakout_oi_confirmed_5m` replay acceptance rules, and a
  follow-up read-only feasibility probe found runtime-style OI-confirmed rows
  far below the Stage 0R sample floor (`n=9` pooled; every symbol `<100`) with
  negative rough gross 15m. It cannot be used as promotion evidence.
- ✅ **`[55]` fill-lineage source-cleared**: patched invariant on `trade-core`
  PG proves `chains_with_real_fill_report=25/25` fully-filled plan chains,
  `full_plan_fills_missing_report=0`; 13 partial chains are diagnostic.
- ⏳ **A-group alpha-source invariant**: `declared_alpha_sources()` vs real
  logic re-check remains deferred until new alpha candidates land.
- 🟡 **W-AUDIT-4b corrected scope** remains active via §11.2 remaining
  retained tables/views/drop scope; `P1-WA4B-INSERT-1` is completed.
- ✅ W-AUDIT-3b runtime smoke, F-08 cron fire, and
  `P0-MIT-LABEL-CLOSE-TAG-1` writer fix are completed; residual edge risk is
  tracked by `P0-EDGE-1`.

---

## §6 Current W-AUDIT Priority Delta

Completed Sprint N+0 / N+1 D+0 execution ledgers and Post-MAG-084 Wave 1
planning are archived in
`docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`.

Priority verdict after PM/PA/FA cross-check:
1. **True-live remains blocked** by `P0-EDGE-1`, `P0-LG-1/2/3`, and
   `P0-OPS-1..4`; none of the 2026-05-15 runtime/doc fixes grant live authority.
2. **Stage 1 demo micro-canary is blocked**, not active execution. A4-C is
   GATE-RED, and the OI-confirmed 5m packet is underpowered/negative until a
   future full Stage 0R replay returns green.
3. **Alpha path priority**: A4-C revise-or-archive / diagnostic maturity,
   then W-AUDIT-8a Phase C0 liquidation revival inventory, Phase C1 only after
   BB standalone topic proof, then `8c` Liquidation Cluster and `8b` Funding
   Skew strategy specs. The business-chain root cause is still lack of
   non-textbook alpha.
4. **Runtime hard FAIL**: clear `P1-INTENT-FREEZE-27` before any canary or
   promotion-sensitive runtime action; then keep `P1-FILL-LINEAGE-MONITOR`,
   `P1-STARTUP-BURST-MITIGATION`, current-log V083 follow-up, and
   `P1-W6-5-ML-METRICS` behind the alpha/live blockers.
5. **Maintenance**: P2 hygiene, GUI/AI UX, and old worktree dump cleanup stay
   below alpha/LG/ops gates.

---

## §7 W-AUDIT-6d Mid-Ground Summary

Detailed 保 6 / 砍 6 ledger and DSR K -12 derivation are archived in
`docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`.

Active rule that remains: the 6 polishing items are still rejected unless a
future QC/PM decision reopens them; do not add per-symbol/per-threshold sweeps
that inflate DSR trial count.

---

## §8 D-02 Layer 2 Manual 7d 試運行 SOP（Operator 自執行）

完整 6 step SOP 見 FA report `2026-05-09--full_dispatch_business_chain_validation.md` §2。摘要：

1. **API key 取得**：Anthropic Console → Create Key（命名 `openclaw-layer2-manual-7d-trial`，monthly budget $5）
2. **寫入**：`echo "sk-ant-xxx..." > $OPENCLAW_SECRETS_ROOT/secret_files/anthropic/api_key && chmod 600`
3. **Manual trigger 7d daily**（每天 1 次任意時間）：`curl -X POST http://localhost:8000/api/v1/layer2/run_session -d '{"trigger_kind":"manual_daily_probe","scope":"L1_triage","max_cost_usd":0.50}'`
4. **4 metric 7d 觀察**：cost_today / decisions_assisted / avoided_loss / false_positive_rate
5. **Pass**: alpha > 2× cost + false_positive < 40% + 0 critical incident；**Fail**: alpha < cost OR false_positive > 60% OR ≥1 layer2 建議致 > 5 USDT 虧損
6. **Fail rollback**: `rm api_key && restart_all.sh --keep-auth`

**FA constraint**（invariant 15）：D-02 SOP 不可自動化為 cron / event-trigger（會違 ADR-0020 manual+supervisor-only）。預期 +2-5 USDT/week alpha contribution；如 7d < 1 USDT/week 不值人工 fixed cost，建議 abort。

---

## §9 Dormant D-XX Section（FA §5.2 必 explicit + reason）

| D-XX | Description | Status | Reason | Earliest reactivate |
|---|---|---|---|---|
| D-13 | Cognitive Modulator | DORMANT | 3-Tier `consecutive_loss/weekly_pnl` 數據源未接齊 + alpha 無依賴 | Sprint N+8+ |
| D-14 | DreamEngine 完整自主進化 | DORMANT | Foundation Model + L4 跨 strategy meta-learning（ADR-0020 限制 manual）；Foundation Model 未 ready | long-tail |
| D-15 | OpportunityTracker 全 Agent 注入 | DORMANT | 不影響 supervised live；Sprint N+5 可選 | Sprint N+5 可選 |
| D-16 | openclaw_core 9 模組 sunset cleanup | DORMANT | ADR-0015 已標 permanent sunset candidates | Sprint N+6+ |
| D-17 | Layer 2 自主推理循環自動觸發 | **PERMANENT DORMANT** | ADR-0020 manual+supervisor-only by design | **不解** |

**FA constraint**：靜默漏寫 = 6 個月後 lobby 重新 review；explicit 標 dormant + reason + earliest reactivate = 防 strategy drift。

---

## §10 P0 — True-Live Blockers

| ID | Status | Task | Acceptance |
|---|---|---|---|
| `P0-AGENT-1` | ✅ DONE 2026-05-11 | Runtime Agent Decision Spine lineage | WINDOW_PASS 簽於 `2026-05-11--w_c_window_pass_signoff.md`；post Caveat 1+2 fix `ccf7a4bc` empirical 證實。 |
| `P0-AGENT-2` | ✅ DONE 2026-05-11 | MAG-082 Stage 2 evidence window | 51h pre-fix + post-deploy adversarial SQL missed_n=0 entry / 14.7 state_changes/min；QA re-audit PASS。 |
| `P0-AGENT-3` | ✅ DONE 2026-05-11 | MAG-083 final release audit | 三角 audit (QA + PA + QC) 全 APPROVE；reviewer brief 5 章節 per `2026-05-11--w_d_mag084_signoff.md` §4。 |
| `P0-AGENT-4` | ✅ DONE 2026-05-11 | MAG-084 operator sign-off | Signed `docs/governance_dev/2026-05-11--w_d_mag084_signoff.md`；W-D wave CLOSED。 |
| `P1-STABLE-ID-1` | ✅ DONE 2026-05-11 | compute_spine_ids() helper 抽出（從 E5 D-1 P2 升 P1 per PA） | Done via `b830e3fa` + E2 lint fix `e40b2a76`; Wave 1 A closed in `d069b9e8`. |
| `P1-RCA-1` | ✅ RCA DONE 2026-05-11 | RCA QA R-1: 6 orphan ER + 1 missed entry 4-min burst | Verdict systemic; follow-up implementation tracked by `P1-FILL-LINEAGE-*`, `P1-HEALTHCHECK-55-INVARIANT`, and `P1-STARTUP-BURST-MITIGATION`. |
| `P1-W-AUDIT-3b-SMOKE` | ✅ DONE 2026-05-15 | W-AUDIT-3b runtime smoke (FA-1) | ssh trade-core RouterLeaseGuard Drop test PASS + `[55] chains_with_lease=89` + `pytest -k fail_closed` PASS；commit `22efd9de` smoke verify |
| `P1-LG-DESIGN` | ✅ DESIGN DONE 2026-05-11 | PA design LG-2/3/4 tech plan | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md`; implementation tracked by `LG-1/2/3`. |
| `P1-FILL-LINEAGE-DROP` | ✅ SOURCE/REGRESSION/DEPLOY DONE 2026-05-11 | Spine channel silent-drop fix (Option F4 B-2+B-3 hybrid) | `e17ead2b` + E4 READY/PASS; post-deploy startup burst residual tracked by `P1-STARTUP-BURST-MITIGATION`. |
| `P1-FILL-LINEAGE-MONITOR` | ⏳ post Wave 1.6 deploy | Drop counter healthcheck wiring | 3 SPINE_CHANNEL_* counter 已暴露 accessor，healthcheck [N] 接 + 5/min WARN 閾 |
| `P1-HEALTHCHECK-55-INVARIANT` | ✅ SOURCE-CLEARED 2026-05-15 | Redesign / clear [55] WARN gate as invariant test (QC S3) | Code now gates on fully-filled plan chains (`cum_fill_qty >= plan_qty * 0.999`) instead of `chains_with_real_fill_report / complete_chains >= 50%`. Patched `trade-core` DB verification PASS: `25` fully-filled chains / `25` real-fill ER / `0` missing; `13` partial chains surfaced separately. Per-fill partial ER remains future hardening, not current Stage 1 demo blocker. |
| `P1-INTENT-FREEZE-27` | 🟡 DEPLOYED; POST-GRACE PENDING 2026-05-15 | Full passive healthcheck hard FAIL `[27] intents_counter_freeze` | RCA found BTCUSDT exchange precision rounding (`final_qty <= 0`) after approved risk verdict, not a whole `trading_writer` outage. Source fix records this path as rejected qty=0 audit intent/verdict and defers Approved verdict persistence until a dispatchable `final_qty > 0`. Rebuilt on `trade-core` at `7b33ab2e`; immediate `[27]` direct probe PASSed under fresh-restart grace, so post-grace `[27]` PASS still required before canary/promotion-sensitive runtime action. |
| `P2-DUAL-RAIL-ORDER-ID` | ✅ DONE 2026-05-15 | demo + live_demo 共享 order_id 衝突解 | `2f1c385b` adds mode prefix to `order_link_id`. |
| `P2-RUNTIME-SHADOW-SPLIT` | ✅ DONE 2026-05-15 | runtime_shadow.rs 828 LOC > 800 警告 split | `122015b7` split runtime_shadow.rs under warning threshold. |
| `P3-AGENT-SPINE-BENCH` | ⏳ scheduled N+3 | emit_entry_lineage / emit_fill_completion bench harness | E5 注：當前只有 tick_pipeline hot_path_baseline；補 1000×100 sample SLA monitoring |
| `P3-SPINE-COUNTER-CACHE-ALIGN` | ⏳ scheduled quiet period | 3 AtomicU64 counter `#[repr(align(64))]` cache line | E5 cosmetic; 10 min fix; ~50-200ns extra latency 降到 0 |
| `P1-STARTUP-BURST-MITIGATION` | ⏳ scheduled post Wave 2 | Engine restart 後 startup burst 1-min window 仍 silent-drop 23.5% real-fill ER (Wave 1.6 deploy 16:22:52 UTC 實證 4/17 drops) | Cap 8192→32768 OR retry 3×50ms→5×100ms 500ms budget OR staggered engine bring-up；steady-state 0% drop 證 Wave 1.6 fix 有效 |
| `P1-V083-HALT-SESSION-CTX` | 🟡 SOURCE/TEST CLOSED; CURRENT LOG CLEAN 2026-05-15 | halt_session close fill 曾可繞過 synthetic `entry_context_id` fallback，導致 `chk_fills_close_has_entry_context_id_v083` 每 2s 重試卡 writer | Source fix: `step_6_risk_checks.rs` halt loop 改走 `resolve_close_entry_context_id()`；回歸 test PASS + grep 舊 fallback 0 hit。2026-05-15 current `/tmp/openclaw/engine.log` grep showed no `chk_fills_close_has_entry_context_id_v083` / `halt_session` hits; keep one full-healthcheck follow-up before deleting the row. |
| `LG-1` H0 production caller | 🔵 Wave 2.2 dispatched 2026-05-11 | T1+T2+T3+T4 E1×4 parallel IMPL | per PA plan §1.4 |
| `LG-2` Provider pricing binding | 🔵 Wave 2.2 dispatched 2026-05-11 | T4 RiskConfig 先 → T1+T3 parallel → T2 startup assertion 序列 | per PA plan §2.4 |
| `LG-3` Supervised live SM | 🔵 Wave 2.1 PA spec phase dispatched 2026-05-11 | PA spec doc 1-1.5d → QC+BB+MIT parallel review → PA spec v2 → Wave 2.4 E1×7 IMPL | per PA plan §3.6 + §6.1 + §6.4 |
| `P0-EDGE-1` | ACTIVE | Edge net-positive decision | Strategy edge must be positive or scoped to limited supervised path before true-live. **Root cause linked to `P0-MIT-LABEL-CLOSE-TAG-1` 1-day fix（最高 ROI）**。 |
| `P0-MIT-LABEL-CLOSE-TAG-1` | ✅ DONE 2026-05-10 | `label_close_tag` NULL writer fix（attribution real root cause） | Post-M3 chain integrity era-split reached 100% per `[65]` / invariant 21 (`db17e205`); P0 edge remains active separately. |
| `P0-LG-1` | ACTIVE | H0 blocking production caller | H0 wired into production decision path with metrics + fail-closed. |
| `P0-LG-2` | ACTIVE | Provider pricing binding | Fee/pricing source bound, freshness checked, asserted at startup. |
| `P0-LG-3` | ACTIVE | Supervised-live state machine | Live authorization, lease, drawdown, revoke, operator approval explicit + tested. |
| `P0-OPS-1..4` | ACTIVE | HTTPS / credential rotation / legal+ToS / first-day runbook | Required before true-live. |
| `P0-DECISION-AUDIT-1..5` | DONE 2026-05-09 | AMD §5.4.1 / shadow_mode TOML / §三 stale 防線 / 5 策略 verdict / openclaw_core+Layer2 sunset | AMD-2026-05-09-02 + ADR-0015/0017/0020 + W-C operator auth file。 |
| `P0-DECISION-AUDIT-6` | DONE 2026-05-09 | **W-AUDIT-6d mid-ground verdict**（保 6 / 砍 6） | Operator confirmed 2026-05-09 mid-ground (PM session)；保 6 結構性 + 砍 6 polishing；DSR K -12 量化（§7）。 |
| `P0-DECISION-AUDIT-7` | DONE 2026-05-09 | **W-AUDIT-4 ML 基座併入 W-AUDIT-8f (R-3) Hypothesis Pipeline** | Operator confirmed 2026-05-09 (PM session)；W-AUDIT-4b corrected scope = 3 retained INSERT tables + 2 views + 1 dropped/no-DDL；Decision-3 longer-wave Hypothesis Pipeline remains W-AUDIT-8f。 |
| `P0-NEW-ISSUE-1` | DONE 2026-05-09 | LiveDemo pipeline auth_missing → restored | `[56]` PASS via signed `/api/v1/live/auth/renew`；RCA: `manual` sentinel；`--keep-auth` warns when auth absent. |
| `P0-NEW-VULN-1..2` | DONE 2026-05-09 | launchd plist HIGH / lease audit runtime emit HIGH | Mac launchd 127.0.0.1 binds; `100.91.109.86:8000` Tailscale; lease_transitions `BYPASS` rows=103. |
| `P0-AUDIT-NEW-LG-X-05` | DONE 2026-05-09 | SPECIFICATION_REGISTER LG-X-05 缺 + LG-X-04 編號錯位 | LG-X 完整登記。 |
| `P0-V2-NEW-1-DONCHIAN-LEAK-BIAS` | DONE 2026-05-09（**4-agent fact-check 撤銷 stale belief**） | `IndicatorEngine::compute_all` 自 `75741eff` (2026-04-28) 起呼 `donchian_prior()` leak-free 11 天；`ad14db07` 僅補 regression test；QC v2-NEW-4「runtime contaminated」判定為過期 contaminated belief（commit `6afad6e8`）。 | n/a |
| `P0-V2-NEW-2-STRATEGIST-CAP-NO-GATE` | ✅ DONE 2026-05-10 | F-strategist-cap 30→50 is a `wide_parameter_adjustment` skill, not a supervised gate. ADR numbering drift is closed by ADR-0022 (ADR-0021 was already alpha-source architecture). | ADR-0022 + ARCH-04 + AMD-2026-05-10-03/04 landed; no active blocker remains. |
| `P0-V2-NEW-3-DSR-PBO-EVIDENCE-CRON` | ✅ RUNTIME APPLIED 2026-05-15 | DSR/PBO promotion gate + evidence push chain source/test closed; V079 is applied on `trade-core` and `learning.strategy_trial_ledger` has 16,212 rows. | Runtime V079 concern closed; future Stage 1/2 promotion callers still require green demo evidence and governance gates. |
| `P0-V3-MIT-ROOT-CAUSE` | ✅ DONE | = `P0-MIT-LABEL-CLOSE-TAG-1`（cross-reference）| Closed by post-M3 chain integrity evidence; residual alpha/edge risk tracked by `P0-EDGE-1`. |
| `P0-V3-V079-NOT-APPLIED` | ✅ DONE 2026-05-15 | Superseded stale source-only note. `trade-core` `_sqlx_migrations` max version is 90; V079 is applied; `learning.strategy_trial_ledger` exists with 16,212 rows. | Archived from active queue. |
| `P0-V3-CRON-NOT-INSTALLED` | ✅ DONE 2026-05-09 | F-08 5 ML cron `17 3 * * *` installed and 24h fire verified. | invariant 18 closed. |
| `P0-V3-PA-SPEC-FIX` | ✅ DONE 2026-05-10 | BB v3 pushbacks were adopted: Bybit V5 orderbook uses L50 not L25; `liquidation_pulse` is `requires_revival` dormant; basis remains observation-only until mainnet spot capability. | Verified by BB final compatibility review; future Phase C/C+1 implementation still needs BB/MIT review. |
| `P0-V3-ADR-0021-ARCH-04` | ✅ DONE 2026-05-10 | ADR-0021 alpha-source architecture, ADR-0022 strategist cap, ARCH-04, CONTEXT alpha-source terms, AMD-2026-05-10-03, and AMD-2026-05-10-04 landed/indexed. | Historical row archived; ARCH-04 Stage 1 paper semantics later superseded by AMD-2026-05-15-01. |
| `P0-V3-ENGINE-RESTART` | ✅ STALE/CLOSED 2026-05-15 | Old "engine still 5/8 binary" note is no longer current. `trade-core` runtime is alive on the current source line for 2026-05-15 checks; paper remains disabled by design. | Do not use as an active blocker; Linux dirty WIP now blocks clean source sync separately. |

---

## §11 P1 — Next Engineering Queue

### §11.1 Sprint N+0 Active

Archived as completed in
`docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`. Current
active work starts at §10 / §11.2 / §11.3.

### §11.2 W-AUDIT-4b corrected retained tables/views/drop scope（invariant 19）

| ID | Object | Corrected class | Owner | Notes |
|---|---|---|---|---|
| `P1-WA4B-INSERT-2` | `learning.cost_edge_advisor_log` | retained INSERT table / row-growth confirmed | E1 | Writer live at `cost_edge_advisor/mod.rs`; 2026-05-14 runtime row-growth confirmed: 6091 rows. Current demo `[cost_edge].enabled=false`, so rows are `Disabled` / `ratio=NULL`; ratio-present rows require a separate config decision. |
| `P1-WA4B-INSERT-3` | `observability.drift_events` | retained INSERT table / readiness gated | E1 | Writer exists in `drift_detector.rs` and is spawned in `tasks.rs`; it depends on active `feature_baselines` and the configured ADWIN burn-in (default 30d). Do not remove burn-in without operator approval. |
| `P1-WA4B-VIEW-1` | `learning.mlde_edge_training_rows` | companion VIEW | E1/MIT | Read-only projection, not an INSERT path. Keep contract under ML training-data healthchecks. |
| `P1-WA4B-VIEW-2` | `learning.scorer_training_features` | companion VIEW | E1/MIT | Read-only projection, not an INSERT path. Full unbounded counts are expensive; use bounded/metadata probes. |
| `P1-WA4B-DROP-1` | `learning.scorer_predictions` | dropped / no-DDL target | E1/MIT | Dropped by V069; no producer wiring target unless a future spec recreates it. |

### §11.2.1 Completed W-AUDIT-4b P1 Items

| ID | Completed at | Evidence |
|---|---|---|
| `P1-WA4B-INSERT-1` | ✅ DONE 2026-05-15 13:13 UTC / 15:13 Europe-Madrid | Fixed by commit `83afb318` via `helper_scripts/cron/feature_baseline_writer_cron.sh` on `trade-core`; restored 646 active `observability.feature_baselines` rows covering 19 symbols × 34 feature names. Standalone `[67] feature_baseline_readiness` now PASSes with `active_rows=646`, `active_symbols=19`, `feature_names=34/34`, and 34-dim online vectors. |

### §11.3 P1 — Other Active

| ID | Priority | Task | Notes |
|---|---:|---|---|
| `P1-W6-5-ML-METRICS` | 2 | W6-5 sample_weight ratio sensitivity + 5 ML pipeline metrics acceptance | Preserved from archived §6.6 MIT MUST 3; do not lose this active signal during TODO cleanup. |
| `P1-CRON-ML-1` | DONE | F-08 5 ML cron 24h fire 驗（cron 已 install at `17 3 * * *`） | invariant 18 says 24h fire verified; V079 runtime concern is closed as of 2026-05-15. |
| `P1-AUDIT-RUNTIME-3` | DONE | W-AUDIT-3 + W-AUDIT-3b（mounts W-A close-out + W-B regression） | W-AUDIT-3b runtime smoke done 2026-05-15; residual `[55]` gate tracked in §10. |
| `P1-AUDIT-PERF-5` | 3 | W-AUDIT-5a/5b 性能/結構/CI urgent | 剩 F-20 909MB damaged dump drop ops |
| `P1-AUDIT-AI-UX-7` | 3 | W-AUDIT-7c GUI/UX 收口 | F-07 ANTHROPIC_API_KEY + cea-env restart |
| `P1-DATA-1..3` | 3 | Runtime-reloaded WARN cluster + low-sample attribution watch + scanner opportunity calibration watch | DONE source-fixed; row rolloff monitor |
| `P1-EDGE-1..2` | 3 | ma_crossover/grid blocked_symbols 已 frozen + funding_arb 14d audit 2026-05-16 | 維持 freeze + 2026-05-16 audit |
| `P1-LG-5` | 4 | LG-5 reviewer maturity watch | source active; audit-row health |
| `P1-FAKE-1` / `P1-OPENCLAW-3/6/7` / `P1-AGENT-OBS-1` / `P1-AGENT-RUNTIME-1` / `P1-DATA-4` / `P1-REPLAY-1/2` | DONE | （詳細歷史見 git history `e7d58774`）| |

### §11.4 P0-MICRO-PROFIT — 微利根因治本路徑（2026-05-11 QC audit 拍板）

**Background**：QC 2026-05-11 audit verdict — 「為何盈利都是超微利潤」+「能否放大」。判定：當前 5 textbook 策略 7d EV<0 (-17.82 bps demo)，**任何 sizing 槓桿 L>1 必放大虧損**（數學常數）。先修 alpha，再談 size。

**5 root cause + 占比**：
1. **Alpha 結構性缺失（~60%）** — 5 textbook 策略 post-publication decay
2. **Account size × 0.1% TOML 物理上限（~20%）** — $591 × 0.1% = $0.59/trade 設計上限
3. **Fee drag（~10%）** — 10.4% taker remnant + PostOnly missed-trade
4. **Signal target tight 設計（~5%）** — grid 22bps / bb 1-2σ / ma sub-1ATR
5. **Slippage + queue position adverse selection（~5%）**

**治本路徑 = PA R-1/R-2/R-3 redesign（已映射 W-AUDIT-8a..8f wave 矩陣）**：

| ID | Task | Spec source | ETA |
|---|---|---|---|
| `W-AUDIT-8a` Phase A | trait skeleton + 5 strategies declare alpha sources | DONE 2026-05-10 Sprint N+0 closure | ✅ |
| `W-AUDIT-8a` Phase B/C/D | Tier 2 panel collector + Tier 3 microstructure + Tier 4 information flow | Sprint N+1 W2 起逐步 IMPL | 4-6 sprint |
| `W-AUDIT-8b` (A4-A) | Funding Skew Directional 新策略（R-1 IMPL）| W-AUDIT-8a Phase B 後 | N+4 |
| `W-AUDIT-8c` (A4-B) | Liquidation Cluster Reaction 新策略 | W-AUDIT-8a Phase C 後 | N+3 |
| `W-AUDIT-8d` (A4-C) | BTC→Alt Lead-Lag 新策略 | W-AUDIT-8a Phase B 平行 | Sprint N+1 W2（fast-track）|
| `W-AUDIT-8e` (R-2) | Strategist Alpha Source Orchestrator | W-AUDIT-8b/8c/8d land 後 | N+3-N+4 |
| `W-AUDIT-8f` (R-3) | Hypothesis Pipeline first-class（含 W-AUDIT-4 ML 6 dead schema 併入）| 序列化於 R-2 後 | N+4 |

**Total ETA = 12-17 sprint（3-4 個月）** — 真實 gross 轉正最早窗口。

**Operator 5 zero/small cost actionable（2026-05-11 拍板）**：
1. ✅ **DONE**：修 `feedback_position_sizing` memory drift（3% → 註明 SSOT 0.1%/0.05%）
2. ⏳ **PASSIVE wait**：等 7d 重測 §三 [40]（24h MLDE +8.75bps 是 transitory 還是穩態）— 2026-05-17 自動收口
3. ⏳ **INFO gathering**：查 Bybit fee tier 距 VIP1 還差多少 30d trading volume（被動 ROI ~0.5-1 bps RT）
4. ⏳ **PASSIVE wait**：TONUSDT 30d evidence → P1-CONDITIONAL-WATCH freeze decision（2026-06-09 收口）
5. ✅ **DEFER 記錄**：D/E sizing 槓桿（volatility scaling / edge-weighted）等 ML calibration N≥200 — 寫入 backlog 防過早 commit

**11 sizing 槓桿全 REJECT in current EV<0 state**（A/B/E/F = REJECT；C/I = CONDITIONAL；D = NEUTRAL；G/H/K = DEFER；J = APPROVE 被動）。

**Operator 守則**：
- 不要看見 memory「3%」就直接套到 TOML（必先讀 risk_config_*.toml SSOT）
- 任何「升 TOML sizing」提案在 EV<0 條件下 = 災難（先修 alpha）
- 信 config，不信 memory（per `math-model-audit` S1）

**Source**：`srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-11--p1_micro_profit_amplification_math_analysis.md`（待 QC commit）

---

## §12 P2 — Maintenance Backlog

| ID | Task | Trigger |
|---|---|---|
| `P2-LEASE-1` | Clean terminal `DecisionLeaseSm.objects` Vec entries | If long soak shows memory growth or before high-volume live |
| `P2-STRUCT-2` | Zombie/deprecated code inventory | Next architecture hygiene sweep |
| `P2-AUDIT-DEAD-CODE` | openclaw_core 9 模組 sunset (D-16 dormant，§9) | ADR-0015 + AMD-2026-05-09-02 accept; Sprint N+6+ |
| `P2-AUDIT-VERIFY-3` | W-AUDIT-4 dead schema 真實 fix → **mounted into `W-AUDIT-8f` (R-3) Hypothesis Pipeline per Decision-3 (P0-DECISION-AUDIT-7)** | Sprint N+5 |
| `P2-V19-CYCLE` | ✅ DONE 2026-05-15 — TODO cleanup/archive cycle | `docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`; TODO under 700-line hygiene target. |

### §12.1 Sprint N+2 P2 Backlog (PA 2026-05-11)

| ID | Task | Status |
|---|---|---|
| `P2-N2-1` | btc_lead_lag.rs 4-split (producer/ingest/snapshot/db_writer) | 🔄 IN FLIGHT (Codex) |
| `P2-N2-2` | w2_paper_edge_report.py 4-split (metrics/render/smoke/report) | ✅ DONE 2026-05-14 (Codex; commit subject `[ae-pm] P2-N2-2: w2_paper_edge_report.py 4-split`) |
| `P2-N2-3` | Layer 2 helper should_spawn_btc_lead_lag_producer extraction | ✅ DONE `fca1aec9` |
| `P2-N2-4` | CI grep rule for stable_id literal duplication guard | ✅ DONE `155bad6d` |

---

## §13 Push Back / Risk 治理記錄（不可漏失，FA §5.6）

### PA Push Back（已 RESOLVED 2026-05-09 operator (a)）
- **原 risk**：Sprint N+0 5/5 HOT capacity = 任一 E1 故障 = 阻塞 critical path
- **Operator 拍板 (a)**：提供 1 stand-by E1，Sprint N+0 capacity 升級為 6 並行（5 active + 1 stand-by）
- **記錄**：v19 §0 Sprint Banner / §5.4 invariant 22 / §6 Day 0-3 dispatch

### FA Push Back（採納，記入治理）
1. Track W vs Track A 預算 — Track W 92h 是 supervised live 前置門檻（合規/安全/可觀測 baseline），**不能被 Track A lobby 取代**
2. D-02 SOP 預期上限 +2-5 USDT/week；若 7d < 1 USDT/week 不值人工 fixed cost，建議 abort
3. A/B/C 候選預期 +3-7% 業務鏈是中位估，新 alpha source **0% PASS 率歷史不支持「三都 PASS」樂觀情境**
4. W-AUDIT-6d 砍 6 polishing 是 DSR 數學意義 right move（K -12），不是省工時妥協

### 4-agent loss audit cross-fact-check（已撤銷的 stale belief）
- **QC v2-NEW-4 Donchian「runtime contaminated」過期 contaminated belief**：MIT 校核 + PM 直接驗證確認 runtime 自 `75741eff` (2026-04-28) 起 leak-free 11 天；`ad14db07` 僅補 regression test。後續 audit / push back 不可再引此 finding 為 active runtime issue。

---

## §14 Schedule

| Date | Work | Gate |
|---|---|---|
| 2026-05-10..16 | Sprint N+0 W1-W2 FOUNDATION HEAVY | Closed; detailed ledger archived in `docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md` |
| 2026-05-16 | funding_arb 14d audit | verification/history; retirement decision in AMD-2026-05-09-02 / ADR-0018 |
| 2026-05-17..23 | Sprint N+1 ALPHA SURFACE PANEL WIRING | 8a Phase C/D prep + A4-C diagnostic maturity/revise-or-archive; Stage 1 demo only after future green Stage 0R (`[55]` source-cleared) |
| 2026-05-24..30 | Sprint N+2 8d follow-up + 8a Phase D + Stage 2 demo cohort 14d | Stage 2 only from Stage 1 demo empirical evidence |
| 2026-05-31..06-06 | Sprint N+3 8c (Liquidation) IMPL + 8e (R-2) spec + Stage 3 demo full | |
| 2026-06-07..13 | Sprint N+4 8f (R-3) spec + 8b (Funding Skew) IMPL + 8e IMPL + Track W 收尾 | Track W 全 closed |
| 2026-06-14..20 | Sprint N+5 8f IMPL + 8g (R-4) spec + first per-alpha-source supervised live | 業務鏈 85-89% |
| 2026-06-15 | Supervised live 樂觀帶（業務鏈 75%+） | conditional on W-AUDIT-1..7 + 5 P0-LG/OPS + W-A/B/C/D PASS |
| 2026-06-30 | Supervised live 中位帶（業務鏈 80%+） | ~40% probability per FA |
| 2026-07-15 | Supervised live 悲觀帶（業務鏈 85%+） | ~25% probability per FA |

---

## §15 Dispatch Rules + Handoff Checks

### Dispatch Rules
- PM-first triage for every wave
- Implementation work: `PM → PA → E1/E1a → E2 → E4 → QA → PM`，roles 跳過需 explicit justify
- Security/deploy/runtime work: `PM → E3 → BB if exchange-facing → PM`
- Quant/data decisions: `PM → QC → MIT → AI-E if model economics matter → PM`
- Commit each green checkpoint with subject and body, push to origin, then sync Linux by fast-forward
- **Commit message 加 `[skip ci]`** 對非 CI-relevant 變更（doc / governance / TODO update / report land），保 CI usage 額度
- Do not rebuild, restart, mutate live auth, change scanner evidence contract, unlock executor shadow, enable lease-router, or add OpenClaw write/proposal routes unless operator explicitly authorizes
- W-AUDIT-6d 砍 6 子項：E2 必 grep blacklist；命中即 reject merge

### Handoff Checks

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

---

## §16 References

### 4-Agent Loss Audit (2026-05-09)
- **PA dispatch plan**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_dispatch_engineering_plan.md` (commit `d3bf7be2`, 689 lines)
- **PA architectural redesign**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`
- **PA merge analysis**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--todo_qctodo_merge_analysis.md`
- **FA business chain validation**: `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_dispatch_business_chain_validation.md` (commit `5a2dee98`)
- **FA dormant alpha inventory**: `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_loss_dormant_alpha_features_inventory.md`
- **FA merge advice**: `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--todo_qctodo_merge_business_chain_advice.md`
- **4-agent loss audit worklog**: `srv/docs/worklogs/2026-05-09--4_agent_loss_audit_and_5_actions.md`
- **QCTODO archived**: `srv/docs/archive/2026-05-09--qctodo_sprint_n0_n5_archive.md`

### Spec / Amendment
- **W-AUDIT-8a spec**: `srv/docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md` (commit `c13c811e`)
- **AMD-2026-05-09-02** (5 P0-DECISION-AUDIT closure): `srv/docs/governance_dev/amendments/2026-05-09--operator_decision_audit_closure.md`
- **AMD-2026-05-09-03** (Graduated Canary Default): `srv/docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md` (commit `b1891023`)
- **ADR-0015** openclaw_core sunset / **ADR-0017** scanner authority retirement / **ADR-0018** funding_arb retire / **ADR-0020** Layer 2 manual+supervisor-only

### Adversarial Verification
- **v3 PM Sign-off summary**: `srv/2026-05-09--audit_fix_verification_v3_summary.md`
- **v2 PM Sign-off summary**: `srv/2026-05-09--audit_fix_verification_v2_summary.md`
- **v1 PM Sign-off summary**: `srv/2026-05-09--audit_fix_verification_summary.md`
- **PA Fix Plan v2 (DUAL-TRACK)**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md`
- **2026-05-08 12-Agent Full Audit + PA Fix Plan**: `srv/2026-05-08--full_audit_fix_plan.md`
- **Verified-closed archives**: `srv/docs/archive/2026-05-09--w_audit_verified_closed_archive_{,v2,v3}.md`

### Bybit / API
- **Bybit API 字典/審計**: `docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`

### Process
- **Operator G3-08 enable evidence**: commit `dddc5dc1` restart_all.sh wire + 2026-05-09 17:27 UTC engine.log `cost_edge_advisor spawned env=1 phase=B_shadow`
