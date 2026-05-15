# CLAUDE_CHANGELOG.md — 開發歷史歸檔

> 從 CLAUDE.md 遷出的 Wave/Sprint/Batch 歷史記錄。新 session 不需要讀此文件，僅供回顧歷史時查閱。
> 最後更新：2026-05-15（Claude/Codex same-page sync）

### P0-MICRO-PROFIT alpha prework — 2026-05-15

**Scope**: Converted the micro-profit question into alpha-path prework without
touching runtime, config, auth, DB, paper, demo, or live execution.

**主要 land**:
- Added W-AUDIT-8a C1 standalone liquidation-topic proof plan and helper
  script for `allLiquidation.{symbol}`. C1 remains blocked until a 24h isolated
  BB proof passes and MIT signs the schema mapping.
- Later addendum: 60s C1 smoke passed as `SMOKE_PASS_NOT_C1_PROOF`; 24h
  isolated `allLiquidation.BTCUSDT` proof started on `trade-core` as PID
  `4100789`.
- Drafted W-AUDIT-8b Funding Skew Directional spec v0.1 as a cross-sectional
  crowding signal, explicitly not a retired `funding_arb` revival.
- Archived A4-C BTC→Alt Lead-Lag from the active promotion path because Step
  5b failed the spec R² archive rule; the panel/producer remains diagnostic.
- Indexed the `P1-A4C-RCA-1` read-only RCA start result: current 7d dry-run and
  finite threshold probe both remain below revive/promotion bands.
- Final RCA addendum: QC/MIT closed `P1-A4C-RCA-1` no-revive; `P1-A4C-REV-1`
  is not opened and A4-C remains diagnostic-only.
- Updated TODO/CLAUDE/active-plan/Codex memory/docs indexes to reflect the new
  alpha order.

**Verification**: docs/static + probe dry-run/compile only. No production WS
topic change, no `OPENCLAW_ENABLE_PAPER=1`, no Stage 1 demo canary, no sizing
or risk edit, no live auth, no DB write, no rebuild/restart.

### Claude/Codex same-page sync — 2026-05-15

**Scope**: Reconciled Claude-facing active state with the latest Codex/TODO
state without deleting historical Claude records.

**主要 land**:
- `CLAUDE.md` now points at `TODO.md` v28 and records `[27]` as post-grace
  closed by the 2026-05-15 18:12 UTC direct PASS probe.
- `CLAUDE.md` records W-AUDIT-8a Phase C0 as source/doc closed, with C1
  blocked on BB standalone liquidation-topic proof.
- `active-plan.md` advanced to v1.4 and removed the stale `[27]` hard-blocker
  wording while preserving Stage 0R / edge / LG / ops blockers.
- Claude/Codex operating memory is aligned on replay-first validation: first
  decide whether replay/counterfactual replay can check the claim; run it when
  applicable, and state explicitly when WS/live-runtime/DB evidence is required.

**Verification**: docs/static sync only. No runtime rebuild/restart, DB write,
auth renewal, paper enablement, demo canary, strategy/risk config change, or
true-live action.

### PM/PA/FA 5-day TODO/MEMORY/README sync — 2026-05-15

**Scope**: Audited the prior 5 days of work quality and reconciled active
state across `TODO.md`, `README.md`, `CLAUDE.md`, `.codex/MEMORY.md`,
`active-plan.md`, and docs index.

**主要 land**:
- `TODO.md` advanced to v25 and removed stale active interpretation for V079,
  engine 5/8 binary, ADR pending, and old 2026-05-09 demo-state notes.
- `README.md` now reflects current console tabs, GitHub Issues active posture,
  and Decision Lease router flag as shadow/evidence rather than true-live auth.
- `.codex/MEMORY.md` and `active-plan.md` now point at TODO v25 and treat
  MAG-083/MAG-084 as closed, while preserving edge/LG/ops gates.
- Latest full passive healthcheck result is recorded as still FAIL because
  `[27] intents_counter_freeze` is now the current hard runtime blocker.
- Added stale-row archive and PM audit report; the OI-confirmed 5m packet is
  indexed as spec-only with `eligible_for_demo_canary=false`.

**Superseded later 2026-05-15**: `[27]` was subsequently source-fixed,
rebuilt at runtime code line `7b33ab2e`, and post-grace closed by direct PASS
probe. Active state is the Claude/Codex same-page sync section above.

**Verification**: PM/PA/FA audit agreement. Direct `trade-core` read-only checks
confirmed V079 applied through migrations max=90 and
`learning.strategy_trial_ledger` rows=16,212. No business code, strategy config,
auth, runtime, DB write, rebuild, restart, paper enablement, demo canary, or
live authority change.

### P1-HEALTHCHECK-55-INVARIANT — 2026-05-15

**Scope**: Cleared `[55] agent_decision_spine_lineage` WARN by replacing the
50%-of-all-complete-chains heuristic with a fully-filled plan invariant aligned
to the current Rust contract (`cum_filled_qty >= plan_qty * 0.999`).

**主要 land**:
- `[55]` now reports `chains_with_plan_order_fill`,
  `chains_with_full_plan_fill`, `full_plan_fills_missing_report`, and
  `partial_plan_fill_chains`.
- The gate blocks only when a fully-filled plan lacks a fill-completion
  ExecutionReport; no-fill and partial-fill chains no longer poison the
  denominator.
- `TODO.md` and `CLAUDE.md` record `[55]` as source-cleared; A4-C Stage 0R
  remains GATE-RED independently.

**Verification**: `python3 -m pytest helper_scripts/db/test_agent_spine_healthcheck.py -q`
PASS (`15 passed`). Patched module executed on `trade-core` against live PG
returned PASS with `chains_with_full_plan_fill=25`,
`chains_with_real_fill_report=25`, `full_plan_fills_missing_report=0`, and
`partial_plan_fill_chains=13`. No runtime config change, engine restart,
auth mutation, DB write, or strategy/risk change.

### Stage 0R Step 5b runtime verification — 2026-05-15

**Scope**: Reran W2 A4-C BTC→Alt Lead-Lag Stage 0R preflight on `trade-core`
after restoring the diagnostic producer with
`OPENCLAW_ENABLE_BTC_LEAD_LAG_DIAGNOSTIC=1`.

**主要 land**:
- Added PM and Operator reports for Step 5b.
- Updated `TODO.md` to record `[57]` PASS, improved expected_dir distribution,
  and continued `eligible_for_demo_canary=false`.

**Verification**: Stage 0R smoke PASS; latest report fetched 5,740 rows and
returned pooled `avg_net_bps=+0.3552`, `PSR(0)=0.5877`, `DSR=0.0000`,
`eligible_for_demo_canary=false`. Direct `[57]` check PASS; `[55]` remains
`WARN_REAL_FILL_PROPAGATION_PARTIAL`. No paper enablement, canary launch,
runtime config change, rebuild, restart, DB mutation, live auth mutation, or
strategy/risk change.

### P1-WA4B-INSERT-1 TODO/CLAUDE Maintenance Sync — 2026-05-15

**Scope**: Moved `P1-WA4B-INSERT-1` out of the active P1 table after the
feature baseline restore was completed in commit `83afb318`.

**主要 land**:
- `TODO.md` now lists `P1-WA4B-INSERT-1` under completed W-AUDIT-4b P1 items
  with timestamp `2026-05-15 13:13 UTC / 15:13 Europe-Madrid`.
- `CLAUDE.md` §三/§十 sprint status now uses the 2026-05-15 W3 status and
  explicitly preserves P0 W3-1 / W3-2 as `ncyu`-blocked.

**Verification**: Docs-only maintenance. No P0 item status change, no runtime
action, no rebuild, no restart, no DB migration, no live auth mutation, and no
strategy/risk change.

### Passive Healthcheck 7108035d Active-Plan Sync — 2026-05-15

**Scope**: Recorded the `trade-core` full unfiltered passive healthcheck result
after commit `7108035d` fixed `[4] phys_lock_runtime` and `[Xb]
pipeline_triangulation` semantics.

**主要 land**:
- `active-plan.md` advanced to v1.1, now sourced to TODO v22 + `7108035d`,
  and no longer lists completed `P1-STABLE-ID-1` / `P1-RCA-1` as available
  work.
- `TODO.md` records the full healthcheck summary: 67 checks = 55 PASS / 11 WARN
  / 1 FAIL, with `[4]` and `[Xb]` PASS and `[67] feature_baseline_readiness`
  as the only hard FAIL.
- The same full run keeps `[55]` as `WARN_REAL_FILL_PROPAGATION_PARTIAL`
  (`24/138` real-fill reports), so the Stage 1 demo canary block remains.

**Verification**: `trade-core` full `passive_wait_healthcheck.py` run via the
canonical wrapper, no `--check` filter, log
`/tmp/passive_wait_healthcheck_full_20260515.log`. No rebuild, restart, DB
mutation, live auth mutation, or strategy/risk change.

### P2-N2-4 stable_id duplication CI guard — 2026-05-14

**Scope**: 新增快速 grep-based CI guard，防止 W-D MAG-083 P1-1 已集中到
`compute_spine_ids()` / `compute_filled_report_id()` 的 Agent Spine stable_id
seed 計算被未來 Rust callsite 重新用 literal `format!("{}:{}:{}:{}"...`
複製，避免 entry/fill audit chain silent drift。

**主要 land**:
- 新增 `helper_scripts/ci/check_stable_id_duplication.sh`，掃描 `.rs` 檔案，
  canonical helper/caller 以外若同時命中 signature pattern 與 stable-id-like
  變數名即 exit 1，並列 offending file:line。
- `.github/workflows/ci.yml` 新增 `stable_id duplication guard` job，push / PR /
  weekly schedule 都會跑，無 Rust compilation。
- 更新 `helper_scripts/ci/README.md` 與 `helper_scripts/SCRIPT_INDEX.md`。

**Verification**: `bash helper_scripts/ci/check_stable_id_duplication.sh` PASS；
`bash -n helper_scripts/ci/check_stable_id_duplication.sh` PASS；`git diff --check`
PASS。No rebuild, no restart, no DB migration, no live auth mutation。

### V083 halt_session entry_context_id source/test fix — 2026-05-12

**Scope**: 修 `RiskAction::HaltSession` close loop 仍用空字串 fallback 的漏網路徑，避免 close fill 撞 `chk_fills_close_has_entry_context_id_v083` 後讓 `trading_writer` buffer 每 2s 重試。

**主要 land**:
- `step_6_risk_checks.rs` halt-session close path 改走既有 `resolve_close_entry_context_id()`，與 commands.rs 的 orphan-safe synthetic fallback 對齊。
- `per_symbol_price_pnl` halt-session 回歸新增 `entry_context_id` 非空斷言，允許真 `ctx-*` 或 synthetic `orphan_recovery_ctx:*`。

**Runtime evidence used**: 2026-05-12 `trade-core` read-only log 顯示 `risk_close:halt_session` close fill 缺 `entry_context_id`，`trading.fills` batch 每 2s 撞 `chk_fills_close_has_entry_context_id_v083`；watchdog 同時記錄多次 snapshot stale / auto-restart。LiveDemo pipeline 另因 `authorization.json` missing 未啟動，需 operator renew，未在本修復中變更。

**Verification**: `cargo test -q -p openclaw_engine test_halt_session_uses_per_symbol_price_not_triggering_tick` PASS；`rg 'get_entry_context_id\\([^)]*\\).*unwrap_or\\(\"\"\\)' rust/openclaw_engine/src/tick_pipeline` 0 hit；`git diff --check` PASS。No rebuild, no restart, no live auth mutation。

### Live/Demo GUI 今日 PnL 口徑修正 — 2026-05-10

**Scope**: 修正 Live GUI / console 側欄「今日淨 PnL」混入 session/lifetime 手續費的顯示錯誤，並補 Demo/Live tab 前後端 endpoint contract。

**主要 land**:
- `trading_true_metrics.py` 新增 `account_metrics_today` + canonical `net_pnl_today`，以 DB 當地日 `date_trunc('day', now())` 聚合 `realized_pnl - fee + funding`。
- `tab-live.html` 頂部 PnL 概覽改讀 `/api/v1/live/metrics` 的 `net_pnl_today` / `account_metrics_today`；不再從持倉 `cumRealisedPnl` 或 `engine_total_fees` 推算今日值。
- `console.html` Live 側欄改讀同一 `net_pnl_today`，與 Live tab 對齊；Demo 側欄仍使用 Demo balance/session 口徑，Demo metrics grid 共享 canonical backend metrics。
- 新增靜態 contract：Demo tab 只讀 `/api/v1/strategy/demo/*`，Live tab 只讀 `/api/v1/live/*`，Live 今日 PnL 不得出現 `cumRealisedPnl` fallback。

**Runtime evidence used**: Linux `trade-core` read-only DB query showed LiveDemo `today_db_tz net=+1.578890`, `rolling_24h net=+1.584620`, `rolling_7d net=-0.549938`, `lifetime fees=45.711300` / `lifetime net=-36.093800`。因此 operator 看到的約 `-45.45` 是舊前端把 lifetime/session fee bucket 當今日淨虧損的錯誤推算。

**Verification**: `pytest test_performance_metrics_gui_contract.py test_trading_true_metrics.py` 10 passed；`pytest tests/static/test_replay_subtab_static_assets.py` 50 passed；`py_compile trading_true_metrics.py` PASS。No restart, no rebuild, no runtime mutation。

### Sprint N+1 D+0 Pre-dispatch Readiness — 2026-05-10

**Scope**: 24 項提前準備完成等待 21:30 UTC HIGH-5 sign-off 後 dispatch fire；HEAD `9695b59a`（v3.8 4 sub-agent: CC + E3 + R4 + W2 v1.2）

**主要 land**:
- W7-3 Option B 補丁 (`b42731f6` PR ready NOT DEPLOYED): ma_crossover.on_rejection 識別 duplicate_position → sync self.positions 補丁式 1-tick defense, +48 LOC strategy_impl.rs + 152 LOC tests, 4 unit test, E1+E2 APPROVE+E4 PASS (Mac+Linux 2639 deterministic identical)
- W7-1 + W2 trait skeleton (`c9fb0b8f` PR ready NOT DEPLOYED): TickContext.position_state per-iteration borrow + BtcLeadLagPanel struct + AlphaSurface field, 16 file +182 LOC, 0 borrow checker, 433+2640+35 PASS
- W6 RFC 3 視角預備立場 (PA + QC + MIT) + W6-1 RFC final verdict draft (8 section, 4 條 verdict statement, Track A/B 拆分 close PA Q3 vs MIT Q2 V086 timing 分歧)
- W6-3a close_tag distribution audit (12+14 enum + V086 spec preview)
- W6-3b enum spec final (5 ambiguous A1-A5 全 ACCEPT MIT, V086 two TEXT column + one-shot 30-90s in-migration backfill)
- W2 A4-C BTC→Alt Lead-Lag spec v1.2 (5 conditions + dual-layer σ + PSR(0) skew/kurt + +15/+5-15/<+5 階梯 gate, V088 加 3 column, MIT C-3 σ verify CONDITIONAL PASS)
- W1 Phase B Tier 2 collector spec v1.1 (BB WS-first revision, Rust panel_aggregator/{funding_curve,oi_delta} 訂閱既有 WS tickers broadcast, rate 100→0 req/s ongoing)
- W7-4 5 策略 systemic position sync audit (HIGH×2 ma_cross + bb_reversion 同結構, W7-2 同 Wave 推 ~15 LOC 提早結 P2-BB-REVERSION-POSITION-SYNC)
- E4 W4 W-AUDIT-3b smoke design (push back: 既有 9 case 已涵蓋, 唯一 gap = RouterLeaseGuard Drop ~40 LOC, 4 invariant acceptance)
- W5 三 P1 specs (CANARY-STAGE-CRITERIA-1 / CANARY-COHORT-FREQ-23 + V089 / DYNAMIC-UNBLOCK-CHECK-1 + V090, ~1460 LOC est, AMD-2026-05-10-05/06)
- N+0 sign-off + N+1 dispatch fire SOP
- CC compliance pre-check APPROVE-CONDITIONAL Score A- 92.0% (vs N+0 A 93.3% -1.3pp)
- E3 security pre-audit ALL PASS (0 CRITICAL/HIGH/MEDIUM, 3 LOW backlog, 5 hard gate 全綠)
- R4 docs audit (docs/README.md addendum + CLAUDE.md §三 [40] update + Active Blockers + §十 v3.7 dispatch path)

### Sprint N+0 Closure — 2026-05-10

**Scope**: W-AUDIT-9 graduated canary 5-stage state machine + W-AUDIT-4b ML pipeline 3-fault fix + W-AUDIT-8a Phase A AlphaSurface trait declare 全 land；commit chain HEAD `b6ed4975`

**主要 land**:
- V80/82/83/84 SQL migrations 全 sqlx success=t auto-migrate (engine restart 09:23 UTC)
- W-AUDIT-9 T1-T7: ExecutorCanaryConfig + CanaryStage enum (Rust schema) + Python stage-aware fail-closed Stage 0 + LeaseScope::CanaryStagePromotion + governance.canary_stage_log + GUI graduated tab + [58] healthcheck
- W-AUDIT-4b M1/M2/M3: decision_features producer (V082) + fill writer (V083 fills.entry_context_id) + reject negative label (V084 + 6 Rust file emit_decision_feature_intent_rejected)
- W-AUDIT-8a Phase A: AlphaSurface trait + 5 策略 declare alpha_sources（Phase B-D 留 Sprint N+1+）
- ARCH-04 graduated canary 5-stage architecture
- ADR-0022 strategist-cap-wide-parameter-adjustment-skill
- AMD-2026-05-09-03 graduated canary default (alpha-bearing)
- AMD-2026-05-10-03 invariant 5 wording 對齊 N+0 actual IMPL (option A)
- AMD-2026-05-10-04 TOML drift fix SOP (option B-later)

**Runtime impact verified**:
- attribution_chain_ok ratio 0.5% (mock baseline) → 100% (grid 199/ma 59/bb_breakout 11) — 後 MIT chain integrity replay 揭露 mock baseline 是誤讀，pre+post V083 真實全期均 100%
- `[40]` 24h MLDE avg_net **-17.82 → +8.75 bps**（翻正）
- `[33]` maker_like 89.6% → 98.1%；fee_drop 59.5% → 84.4%
- 5 ML cron jobs install 後 status=ok 真實 fire (lightgbm via venv fix + optuna install)
- FAIL only 1 cell：live_demo/grid_trading/TONUSDT n=10 avg=-31.23 bps（QC verdict C small-sample 非結構性，P1-CONDITIONAL-WATCH 30d evidence）

**4 final reviews verdict (Sprint N+0 sign-off)**:
- CC: APPROVE-CONDITIONAL Compliance Score A 93.3% (v3 90% → N+0 93.3%)
- QC: APPROVE 3 MED + 4 caveat + 3 push back（mid-ground K -12 是擋槍 / Stage 2/3 sample size vs wall-clock 矛盾）
- MIT: APPROVE FULL post V083+V084 dry-run
- BB: APPROVE 0 Bybit risk

**22 sign-off invariant**: 14 ✅ / 6 DEFER / 2 PARTIAL / 0 FAIL

**4-agent loss audit consensus 維持**: 5 textbook 策略結構性 alpha-deficient（grid + ma + bb_breakout + bb_reversion + funding_arb）；P0-EDGE-1 root closure pending W-AUDIT-8a Phase B/C/D collector + A 群 alpha 候選 8b/8c/8d IMPL（Sprint N+1 W2 A4-C BTC→Alt Lead-Lag fast-track 為首）。

### W-AUDIT-1 docs/governance sync — 2026-05-09

**Scope**：完成 W-AUDIT-1 文檔/治理同步。CLAUDE §三/§四/§五/§十
改為 2026-05-09 實測狀態；新增 W-C lease-router evidence authorization file；
AMD-2026-05-02-01 補 §5.4.1；補 ADR-0015..0019、CONTEXT 詞條、SCRIPT_INDEX、
SPECIFICATION_REGISTER LG-X / SM-03 / EX-03 / ARCH-02/03 / AUDIT-13、
docs/README 2026-05 index addendum、MIT/BB workspace README。

**Runtime evidence used**：Linux `trade-core` source `b91487f2`；watchdog
`engine_alive=true`；runtime env `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow` +
`OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1`；scanner config 無 `[authority]`；
`[55]` PASS with `chains=101` / `chains_with_lease=76` /
`chains_with_report=101`，但 MAG-082 readiness remains
`LINEAGE_READY_NOT_WINDOW_PASS`；passive healthcheck after `[41]` source fix
returned `SUMMARY: WARN`。

**Boundary**：docs/governance only。未 rebuild、未 restart、未改 live auth、
未開真 live API、未改策略/風控參數、未解鎖 Executor order authority、未批准
MAG-083/MAG-084。

### P1 healthcheck FAIL queue cleared + Executor fake-live source fix — 2026-05-07

**Scope**：新增 `TODO.md` `P1-FAIL` 插隊隊列，將當前 Linux
healthcheck FAIL `[Xb]` / `[42*]` / `[50]` / `[51]` 放到 P1 normal work
之前；`P1-FAKE-1` source 修復 Executor fake-live wiring。後續同日已清
P1-FAIL-0..3 的 FAIL blocker：17:51Z Linux healthcheck 回到 `SUMMARY: WARN`。

**Executor fix**：`ExecutorAgent` real IPC path 改為 Rust 實際存在的
`submit_paper_order`，payload 顯式帶 `engine`；`ExecutorConfigCache`
`shadow_mode_provider()` 支持 explicit `demo` / `live` / `live_demo` 查詢，
避免 demo/live_demo flip 被 paper/default cache 吞掉。

**Verification**：Mac targeted Executor tests 25 PASS / 7 skipped；
Linux `trade-core` targeted Executor tests 30 PASS / 2 skipped；`py_compile`
PASS。P1-FAIL queue regression：Mac/Linux targeted tests 96 PASS；Linux
runtime healthcheck 17:51Z `SUMMARY: WARN`，`[Xb]` / `[42]` 不再 emitted，
`[42b]` / `[42c]` / `[50]` / `[51]` 降為可解釋 WARN。API-only reload 已載入
Python-side source；未 engine rebuild、未改 live auth、未 flip Decision Lease、
未改 strategy/risk config。

**Queue RCA**：`[Xb]` 是分母 bug，raw demo intents 被 scanner opportunity
shadow observations 放大，已改為 close-fill-linked intent contexts；
`[42]` 是 LG5 scheduler starvation；`[42b/c]` 是未 settlement 樣本被錯當
attribution failure；`[50]` 是 historical replay failures 已被 newer completed
runs supersede；`[51]` 是 exploration positive LCB 與 calibrated
`opportunity_positive` bucket 混在一起。

### AgentTodo MAG-010..012 durable event-store source wiring — 2026-05-06

**Scope**：新增 default-off `AgentEventStore`，把 legacy/advisory
`MessageBus` delivery 寫入 `agent.messages`，把 `BaseAgent` lifecycle 與
`Conductor.set_agent_state` 寫入 `agent.state_changes`，並把 Strategist /
Guardian / Analyst local Ollama calls 寫入 `agent.ai_invocations`。

**Boundary**：`MessageBus` 仍不是 Agent Decision Spine；DB/serialization 失敗
全部 fail-soft，不阻塞 subscriber、agent lifecycle 或交易 runtime。raw prompt /
raw response 不入庫，只保存 prompt hash、response hash、latency、model、tier、
purpose 與 redacted metadata。Supervisor cloud escalation rows 仍屬 MAG-019。

**Healthcheck / tests**：新增 `[52] agent_event_store_rows`；env=0 PASS-skip，
env=1 檢查 `agent.messages` / `agent.state_changes` / `agent.ai_invocations`
30m 內 row proof，`OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED=1` 時 WARN 升 FAIL。
Mac targeted verification：new tests + affected multi-agent tests 215 PASS，
`py_compile` PASS，`git diff --check` PASS。Linux `trade-core` fast-forward 後
targeted tests 215 PASS、`py_compile` PASS。MAG-013/014 controlled row proof：
strict `[52]` 先 FAIL `messages=0 state_changes=0 ai_invocations=0`；受控
smoke 使用真 `AgentEventStore` / `MessageBus` / `BaseAgent` / `Conductor` 寫入後，
strict `[52]` PASS `messages=2 state_changes=11 ai_invocations=2`。未 restart
服務、未啟用 production continuous flag；supervisor cloud escalation rows 仍屬 MAG-019。

### AgentTodo MAG-015 Sprint A contract addendum — 2026-05-06

**Scope**：凍結 AgentTodo Sprint A 的第一份實作前合同：
`docs/architecture/multi_agent_rework_2026-05-05/2026-05-06--mag015_sprint_a_contract_addendum.md`。
合同定義 `LocalObservation`、`SelfStateSnapshot`、`Diagnosis`、
`EscalationPacket`、`Proposal`、`ApprovalDecision`、`ChannelEvent`、
OpenClaw endpoint allowlist、cloud budget、store ownership、state transitions
與 MAG-010..019 implementation packet。

**Boundary**：docs/meta only。未改 runtime、DB schema、策略/風控參數、live auth、
Decision Lease flag、Gateway channel、proposal write endpoint、rebuild 或 deploy。
OpenClaw Gateway 仍只能作 read/brief/diagnose/proposal/approval relay；MAG-010..014
下一步仍必須先證明 `agent.messages` / `agent.state_changes` /
`agent.ai_invocations` Linux nonzero row proof。

### Scanner Opportunity admission canary — 2026-05-06

**Scope**：把 scanner opportunity 從 read-only shadow 收口到 demo/live_demo
new-open admission canary。這不是孤立新 gate，而是消費既有 typed
`OpportunityDecision.canary_block_new_entry`；close / reduce / protective
paths 不受影響。

**Runtime cost prior**：ScannerRunner 接入 shared `AccountManager`，scanner
opportunity cost 使用 per-symbol taker fee；冷啟動 fee cache 尚空時使用
AccountManager conservative default taker fee，並在
`components.cost_source` 標記來源。

**Row proof**：pre-risk scanner rejects（per-strategy policy、scanner
market gate、opportunity canary）現在寫入 `trading.intents` +
synthetic rejected `trading.risk_verdicts`，且 intent details 保留
`scanner.opportunity`。`[51]` 可對 rejected scanner intents 做後續
counterfactual regret proof；rejected labels 仍需等 `decision_outcomes`
backfill。

**Verification / deploy**：Mac targeted tests PASS：
`scanner::opportunity` 6、`scanner::runner` 4、`scanner::scorer` 32、
`tick_pipeline::tests::fast_track_reduce` 17、`cargo check -p openclaw_engine`、
`test_scanner_opportunity_healthcheck.py` 8。Linux focused tests PASS：
opportunity 6、runner 4、scorer 32、`[51]` Python 8。
Linux `restart_all.sh --rebuild --keep-auth` deployed `98ce3d00`。
Latest scanner snapshot after deploy：85/85 route judgments carry
opportunity, 85/85 carry `cost_source=account_manager_taker_fee`, 85/85
carry canary field；last 30m demo/live_demo rejected scanner intents 78/78
carry scanner opportunity, including 2 `scanner_opportunity_canary` rejects。
Focused `[51]` returned WARN: routes 485/485, scanner intents 50/50,
labels=9<10, rejected_labels=0.

### Scanner Opportunity regret healthcheck — 2026-05-06

**Scope**：續做 scanner opportunity integration audit 的 Step 3，把 `[51]`
從 snapshot / intent / MLDE row-proof 擴展到 rejected scanner intents：
`trading.risk_verdicts` + `trading.intents.details.scanner.opportunity` +
`trading.decision_outcomes` 形成 counterfactual regret proof。Positive LCB
被 reject 但後續 counterfactual net 為正時只回 WARN，不新增交易 gate。

**Durability fix**：`d1754aa6` 將 intent coverage denominator 從
`details ? 'scanner'` 改成 `jsonb_typeof(details->'scanner') = 'object'`，
避免 `{"scanner": null}` 的非 scanner-context intent 造成 false FAIL。

**邊界**：
- 仍是 read-only / shadow-only healthcheck；不改 H0、Guardian、Decision Lease、
  Risk Governor、IntentProcessor。
- 不消費 regret summary 直接開倉；只把 missed / false-block evidence surface 給 operator。
- Rust engine binary 不需 rebuild；`113f345f` 仍是 deployed engine binary。

**Verification / deploy**：Mac `helper_scripts/db/test_*.py` 163 PASS；
Linux `test_scanner_opportunity_healthcheck.py` 8 PASS。Linux focused `[51]`
after `d1754aa6`：WARN，snapshot routes 370/370，scanner intents 6/6，
labels=7<10，rejected_labels=0。Watchdog `engine_alive=true`，demo/live fresh。

### Scanner Opportunity shared cost definition — 2026-05-06

**Scope**：續做 scanner opportunity integration audit 的 Step 2，把 scanner
shadow opportunity 的 fee+slippage round-trip cost 收斂到
`edge_predictor::gate::estimate_round_trip_cost_bps`。Scanner 只額外加當前 spread
作為 scanner-time market cost。

**邊界**：
- 仍是 shadow-only；不新增 gate，不接 `opportunity_lcb_bps` / `admission_hint`
  到拒單 path。
- 不改 H0、Guardian、Decision Lease、Risk Governor、IntentProcessor cost gate。
- 不改 risk config、strategy params、DB schema 或 live authorization。

**Verification / deploy**：Mac + Linux targeted Rust tests PASS：
`scanner::opportunity` 4/4、`scanner::scorer::tests::test_score_ticker_emits_opportunity_shadow_for_each_strategy_judgment` 1/1。
Linux `restart_all.sh --rebuild --keep-auth` deployed `113f345f`，watchdog
`engine_alive=true`，latest scanner snapshot 75/75 route judgments carry
`opportunity` and 75/75 reasons include `cost_model=edge_predictor_round_trip+spread`。
`[51]` remains WARN by design due labels=7<10, with snapshot/intent row proof 100%。

### Scanner Opportunity v1 shadow — 2026-05-06

**Scope**：把 scanner 從「掃市場」補強為 shadow-only「判斷機會」：每個 strategy-symbol judgment 產生中性的 opportunity object，並一路帶到 scanner snapshot、intent details 與 Python control-plane normalized row。

**邊界**：
- 不新增 gate number，不把 `opportunity_lcb_bps` / `admission_hint` 接進拒單 path。
- 不改 H0、Guardian、Decision Lease、Risk Governor、IntentProcessor cost gate。
- 不改 close / reduce / protective exit。
- 歷史 edge 只作 calibration / uncertainty，不覆寫 current-state opportunity。

**Files updated**：Rust scanner config/types/scorer/runner/opportunity module、tick pipeline intent details、Python `rust_scanner_reader.py`、scanner TOML、Rust/Python tests、PM implementation/audit reports。

**Verification / deploy**：local Rust scanner tests 79/79、engine lib tests 2519/2519、release build PASS、Python scanner IPC tests PASS；Linux `restart_all.sh --rebuild --keep-auth` deployed commit `74b986a0`，watchdog `engine_alive=true` with demo/live fresh and paper inactive by design，Linux scanner tests 79/79，Linux Python scanner tests 13/13；latest DB scanner snapshot 10/10 candidates carry `strategy_judgments[*].opportunity`，API sample `has_opportunity=true`。Adversarial grep confirmed no opportunity field is consumed by rejection paths.

### 玄衡 GUI brand cleanup — 2026-05-06

**Scope**：完成 soft rename 的 GUI 收尾，移除入口頁 / console header 的 claw logo，將對外顯示標題改為 **玄衡 · Arcane Equilibrium**。

**邊界**：
- 保留 `OpenClaw Gateway` 作服務名稱。
- 保留 `window.OpenClaw*` JS namespace、`/openclaw` route、`OPENCLAW_*` env、Rust crate / binary names、Bybit connector path。
- 未做 runtime deploy / restart / DB write / live auth mutation。

**Files updated**：static console/login/index/trading/app-gui/governance/monitoring copy + static asset regression test + PM report。

### 玄衡 · Arcane Equilibrium soft rename — 2026-05-06

**Governance change**：正式項目名改為 **玄衡 · Arcane Equilibrium**。

**命名邊界**：
- OpenClaw 保留為控制平面 / Gateway / Console / 通信服務族名稱。
- Bybit 保留為唯一交易所 adapter / connector 名稱。
- 短期不改 `openclaw_engine`、`OPENCLAW_*`、`/tmp/openclaw`、GitHub repo、Linux runtime path、Docker/service name、migration comments、Bybit connector package path。

**Files updated**：README.md、CLAUDE.md、TODO.md、CONTEXT.md、docs/README.md、AGENTS.md、`.claude/agents/PM.md`、`.codex/MEMORY.md`、ADR 0014、PM report/memory。

### §九 LOC governance change 1500→2000 + REF-20 Sprint C accept C1+C2 split — 2026-05-05

**Governance change**：CLAUDE.md §九 硬上限從 1500→2000（operator 決定，REF-20 Sprint C 拍板觸發）。

**Trigger**：PA Sprint C task DAG（`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_c_task_dag.md`）§6.4 揭：`runner.rs` 1466 + R6-T1+T2 ~180 LOC = **1646 LOC 將破舊 1500 cap**。Operator 評估「文件內聚性 > 機械式 LOC 限制」（mirror 2026-05-02 governance change 1200→1500 邏輯），提升至 2000 給 high-cohesion 模組合理 headroom。

**邊界**：
- 警告線維持 800（E2 必標記）
- pre-existing baseline exception clause 條件 (1)+(2)+(3) 同樣適用，閾值同步改 2000
- runner.rs R0-T0 拆檔（抽 IsolatedPipeline + apply_fill 到子模組）仍按 PA 設計做（內聚清理目的，非 LOC 強迫）
- 既 land 但 < 2000 的高內聚模組（如 mlde_demo_applier.py 1542 / governance_hub_live_candidate_review.py 1496 / replay_runner.rs 1432）即時轉 OBSOLETED-BY-GOV-CHANGE，不再列為 §九 violation

**TODO 反映**：v8 → v9 banner；P1-INFRA-3p Sprint C 拆 C1+C2；6 個 P2 ticket 標 OBSOLETED-BY-GOV-CHANGE-2026-05-05（P2-FOLLOW-UP-3 / P2-WAVE-4-W6-REFACTOR / P2-WAVE-6-MLDE-DEMO-APPLIER-SPLIT / P2-R3-FOLLOW-UP-7 / P2-STRUCT-2）；P2-INTENT-PROCESSOR-TESTS-SPLIT 仍 active（2910 > 2000，超 910）但閾值改 2000。

**Sprint C accept C1+C2 split**：
- **C1 (R6, ~6.5d)** Fee/Execution Calibration：grid + ma pilot；apply_fill 真 maker/taker fee + slippage；Rust CalibrationLabelProducer (sample count + freshness + CI bound + regime)；Python writer payload extension；experiment_registry.py execution_confidence write；R6-T7 順帶 LG-3 healthcheck unblock (RFC 0%→70%)；R0-T0 拆檔 runner.rs → isolated_pipeline.rs + apply_fill.rs。
- **C2 (R7, ~6d, C1 closed 後啟)** MLDE/Dream Advisory Integration：dream_engine + opportunity_tracker 升級 evidence_source_tier='calibrated_replay'（依 R6 deliver 的 execution_confidence label）；linucb caller 驗；mlde_demo_applier_evidence_filter Block B integration test；4 producer FK chain audit。
- **0 V### migration** 需求（V036 + V050 + V051 既 land）
- **Pre-DAG advisory wave**：QC + MIT 並行 1d（C1 啟前）；AI-E 1d（C2 啟前）

**設計報告**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_c_task_dag.md`（A 級評級，16/16 root principle 完全合規 + CLAUDE.md §四 硬邊界 0 觸碰）。

**Files updated** (this commit)：CLAUDE.md §九 + .claude/agents/E2.md + .claude/agents/E5.md + TODO.md v9 + docs/CLAUDE_CHANGELOG.md（本 entry）。

---

### REF-20 Sprint B closed — 2026-05-05

**Sprint B 完成定義**：plan §6.R4 UI Enable + §6.R5 Real Decision/Risk Replay Path acceptance 達成。

**完成範圍 (per plan §6 task list)**：

R4 Paper Replay Lab UI Enablement (B1 commit `2a69addb`)：
- tab-paper.html `subtab-btn-replay` 從 static disabled 改 backend-readiness gated
- app-paper.js OpenClawReplaySubtab namespace (5-state machine: empty/running/failed/completed/degraded + 30s periodic poll + last-active-localStorage forced through /health probe)
- 4-cell render: execution_confidence / data_tier / fee_model / calibration_status
- 28/28 static asset tests + XSS guards (≥5 ocEsc/ocSanitizeClass)
- bilingual UI labels reuse `disabled_state.p2_backend_pending` i18n key (no bloat)

R0-T0 LOC budget release (B1 commit `2a69addb`)：
- replay_routes.py 1500 → 1146 (-354 LOC margin for B2 R5)
- 4 sub-router NEW: run_route.py / list_route.py / health_route.py / status_route.py
  (dependency-injection pattern mirror report_route + run_finalize_route)
- audit baseline relax `total_cur_execute_hits >= 5 → >= 0` per R0-T0 retrofit
  (core invariant `leaks=[]` + `audit_ok=True` enforced)
- /cancel + /manifest/verify intentional carve-out per scope

R5 Real Decision/Risk Replay Path (B2 commits `c679a8b4 → a2f819c5 → 4ffb24c4`)：

R5-T1 strategy_adapter.rs (NEW 398 LOC = 244 prod + 154 inline test):
- Strategy trait reuse (0 trait change): `Box<dyn Strategy>` wrapper
- on_tick byte-equal forward strategy.on_tick(ctx) — 0 logic divergence
- StrategyActionTrace::Open carries deterministic SHA-256 intent_signature
  (canonical 6-field: symbol|is_long|strategy|order_type|conf:.4f|qty:.4e)
- ReplayProfile::Isolated constructor reject Live/LiveDemo/PaperLegacy

R5-T2 risk_adapter.rs (NEW 546 LOC = 407 prod + 139 inline test):
- Pure evaluate(&self, intent, snapshot, atr) → RiskDecision (no mutation)
- 6/8 Gate replication from intent_processor::router.rs:
  Gate 1.5 dup / 1.6 neg-balance / 2.0 Guardian (reuse openclaw_core::guardian
  pure 4-check + reducing-path zero-leverage mirror) / 2.5 Kelly (reuse
  ml::kelly_sizer::compute_kelly_qty) / 2.6 P1 cap+qty=0 / 2.7 admission
  (reuse risk_checks::check_order_allowed)
- Gate 1.0 (auth) + 1.4 (Decision Lease) SKIP per V3 §6.2 + AMD-2026-05-02-01
- 2/8 Gate scope-out (per_strategy / governor / D15) — Sprint C R6 follow-up

R5-T3 IsolatedPipeline wire (runner.rs +790 LOC):
- 3 Optional fields (strategy_adapter / risk_adapter / paper_snapshot)
- with_adapter_pipeline() setter + fail-loud snapshot validation
  (NaN balance / empty anchor → ReplayError::InvalidSnapshot per F-3)
- execute() splits: adapter pipeline branch vs synthetic walker fallback
  (preserves proof_1/4/5 e2e byte-equal contract)
- 7 new methods + apply_fill_open/close 4-path mirror paper_state/fill_engine.rs
  (extend / full close / partial close / fresh open)
- ReplayResult.decision_traces field NEW (serde(default) backward compat)
- forbidden_guard runtime trip preserved per V3 §12 #10

R5-T4 CLI integration (replay_runner.rs +418 LOC across 3 rounds):
- ReplayManifest schema: +strategy / starting_balance / strategy_params /
  risk_overrides (all serde(default) optional — xlang fixtures unaffected)
- Always-set adapter pipeline (synthetic walker fallback for in-tree e2e only)
- StrategyFactory::create_with_params + RiskConfig::default()+override

R5-T5 simulated_fills_writer.py decision evidence (+297 LOC):
- extract_decision_traces / build_decision_evidence_index helpers
- map_fill_to_v050_row +decision_evidence kw injects _replay_decision_evidence
  into V050 payload jsonb (PA §6.1: reuse jsonb, no V### migration)

R5-T6 experiment_registry.py config sha256 + blob (+313 LOC):
- Pydantic +strategy_params + risk_overrides optional fields
- Server-side sha256 compute via reuse compute_manifest_canonical_bytes
- INSERT V049 strategy_config_sha256 + risk_config_sha256 with computed values
- manifest_jsonb persists raw blob via _replay_strategy_params + _replay_risk_overrides
- lookup_replay_config_blob helper for downstream

Fix 3 build_default_manifest_payload blob passthrough (route_helpers.py +76 LOC):
- Bridge V049 _replay_* blob → /run handler disk manifest payload
- Closes register-storage to runner-execution gap

R5-T7 acceptance tests (+1210 LOC across 3 NEW files):
- test_strategy_param_delta.py (A4 hermetic: distinct sha / fills differ /
  decision evidence recorded)
- test_risk_param_delta.py (A5 hermetic: distinct sha / tight rejects more /
  rejected_gate in payload)
- replay_runner_e2e_param_delta.rs (Rust proof_7 wiring + proof_8 risk delta)

**Plan §6.R5 acceptance verdict**: A4 + A5 hermetic PASS / proof_7 wiring +
proof_8 risk delta Rust PASS。**push-back accepted**: proof_7 fills divergence
on real fixture (synthetic_btcusdt.json) deferred to Sprint C R6 due to
fixture quality (10-event monotone-up insufficient for grid_levels delta);
wiring round-trip proven, fills divergence requires richer fixture (R6 scope).

**Build + test results (cumulative)**:
- cargo build --release --bin replay_runner --features replay_isolated: PASS
- cargo test --lib (full): 2478 PASS / 0 fail
- cargo test --bin replay_runner: 9 PASS
- cargo test --test replay_runner_e2e: 6 PASS (proof_1-5 + helper)
- cargo test --test replay_runner_e2e_param_delta: 2 PASS (proof_7+8)
- replay_runner symbol audit: 648 symbols / 0 forbidden GREEN
- 0 forbidden import / 0 cross-platform path leak
- Mac pytest replay (full): 196 PASS / 1 skip
- Linux pytest replay (full): 169 PASS / 3 pre-existing fail / 1 skip
- xlang_consistency: 13/13 PASS — CRITICAL invariant maintained throughout

**LOC governance final state (CLAUDE.md §九 1500 hard cap)**:
- replay_routes.py: 1146 (post R0-T0 split)
- route_helpers.py: 1500 EXACT cap (P2-REPLAY-ROUTE-HELPERS-SPLIT ticket)
- experiment_registry.py: 1278 (high-cohesion exception)
- simulated_fills_writer.py: 893 (over 800 warning, R5-T5 scope)
- replay_runner.rs: 1432 (high-cohesion exception)
- 4 sub-router each <500 LOC

**Sprint A still-not-proven items now resolved by Sprint B**:
- A4 actual strategy path: ✓ 3 hermetic + proof_7 wiring
- A5 actual risk path: ✓ 3 hermetic + proof_8 risk delta
- A8 UI usable: ✓ R4 5-state machine + 4-cell

**Sprint A items still NOT proven (Sprint C-D scope per plan §11)**:
- A6 fee-aware PnL: Sprint C R6 (fee model calibration)
- A7 confidence honesty: Sprint C R6 (execution_confidence label none/limited/calibrated)
- A10 ML/Dream advisory boundary: Sprint C R7 (verify_replay_evidence_and_insert)

**Sprint C-D pending dispatch**:
- C = R6 fee calibration + R7 MLDE/Dream advisory integration
- D = R8 maintenance + R9 reality-calibrated usability sign-off (final)

---

### REF-20 Sprint A closed-with-real-evidence — 2026-05-05 02:05 UTC

**Sprint A 完成定義**：plan §6.R3 acceptance "All four must be > 0 after the smoke run" 真實達成。

**最終驗證（QA round 6 final smoke E2E）**：
```sql
SELECT COUNT(*) FROM replay.experiments;       -- 4
SELECT COUNT(*) FROM replay.run_state;          -- 4
SELECT COUNT(*) FROM replay.report_artifacts;   -- 1
SELECT COUNT(*) FROM replay.simulated_fills;    -- 1
```
+ Wave 9 safety (0 trading.fills leak, 0 critical replay audit) + FK lineage 4/4 valid。

**8 commit chain**（按時序）：
1. `c1ab7ea9` R0 (truth reset) + R1 (runtime usability：binary path 5-step fallback + /api/v1/replay/health + restart_all env export + audit script fix + 13 unit tests)
2. `353db3fe` R2 (manifest registry：970 LOC `experiment_registry.py` + `/experiments/register` + `/run` FK guard SELECT FOR SHARE + `/manifest/verify` secrets fallback + 29 tests + canonical_bytes contract)
3. `66b650ea` R3 IMPL (writer 602 LOC + finalize 593 LOC + 19 tests)
4. `cad8ed84` Hotfix L1: Python 3.12 `from __future__ import annotations` + lazy import → FastAPI body 422
5. `e9d547c0`+`2ae93992` Infra fix L2: `OPENCLAW_ENGINE_BINARY_SHA` env injection in restart_all
6. `f51f4e2e` R6+R7 fixes L3+L4: real HMAC sign + sibling key.hex（撞 Sprint 1 Track B fail-closed verifier）+ stderr 寫 disk file (silent-dead 反模式) + 環境注入 + 24 tests + E2 round 1 RETURN 修 (FINDING-1 live profile gate + FINDING-2 SEC-04 detail leak)
7. `3a425447` R8 hotfix L5: signing key provisioning（restart_all 注入 `OPENCLAW_REPLAY_SIGNING_KEY_FILE` env 指 in-tree dev key.hex）
8. `2531c011` R9 hotfix L6: `spawn_replay_runner` 對 `exit=0 within poll grace` 改 sentinel pid=-1 (success path)；`/run` response 加 `subprocess_completed_in_poll` flag

**6-layer blocker chain（每層發現後 fix）**：
- L1 Python 3.12 `from __future__ import annotations` 在 lazy-imported Pydantic body 下 ForwardRef 解析失敗 → FastAPI body 推 Query → 422
- L2 `OPENCLAW_ENGINE_BINARY_SHA` env 缺 → V049 chk_replay_experiments_engine_sha_linux fail-closed → register 503
- L3 `route_helpers.build_default_manifest_payload` 寫 `placeholder_signature_wave6_v042_pending` 撞 Sprint 1 Track B (commit `edf33c0`) `manifest_signer.rs:548-557` fail-closed verifier → subprocess exit=1
- L4 `subprocess.DEVNULL` 隱藏 verify error → operator 必 manual reproduce (silent-dead 反模式)
- L5 `_resolve_manifest_signing_key()` 3-tier chain (env override / secrets dir / fail-closed) 但 Linux 沒 provision → ValueError manifest_signing_key_unavailable
- L6 `spawn_replay_runner` 對 subprocess `exit=0 within poll grace` 回 `(None, "spawn_died_early:exit=0")` failure；synthetic walker 10 events <1.5s 跑完是常態 → 永遠 503

**review chain**：
- PA design × 2 (R3 task DAG + R6 task DAG)
- E2 review × 4 round (R1 / R2 round 1+2 / R3 round 1+2 / R6 round 1)
- E3 audit × 3 (R2 / R3 / R6 — 3 個 PASS-WITH-FIX)
- E4 regression × 4 (R1 / R2 / R3 / R6)
- QA round × 6 (round 1 BLOCK Layer 1 → fix → round 2 BLOCK Layer 2 → fix → round 3 BLOCK Layer 3+4 → fix → round 4 BLOCK Layer 5 → fix → round 5 BLOCK Layer 6 → fix → round 6 PASS)

**LOC final** (CLAUDE.md §九 1500 hard cap)：
- replay_routes.py: 1494 → 1500 (exact cap)
- experiment_registry.py: NEW 970+
- report_route.py: NEW 506
- run_finalize_route.py: NEW 593
- simulated_fills_writer.py: NEW 602
- route_helpers.py: 1224 → 1498
- manifest_signer.py: 443 → 757
- restart_all.sh: 470 → 510

**Sprint A 仍未證明（per plan §11，Sprint B-D scope）**：A4 actual strategy path / A5 actual risk path / A6 fee-aware PnL / A7 confidence honesty / A8 UI usable / A10 ML/Dream advisory boundary。

**重要 invariant 維持**：
- `replay.simulated_fills.evidence_source_tier='synthetic_replay'` 仍**不可作 ML training data**（CLAUDE.md §九 既登記 non-training surface）
- canonical_bytes cross-language byte-equal contract（Sprint 1 F1 retrofit invariant）13/13 PASS 全程維持
- 0 hard-boundary mutation
- 0 cross-platform path leak
- Wave 9 safety SQL 全程 GREEN（0 trading.fills leak, 0 critical replay audit）

**P2/P3 follow-up tickets land in TODO.md**：
- P2-LINUX-FIXTURE-UUID, P2-GRAFANA-DATA-WRITER, P2-FASTAPI-DEPS-SHARED-STATE-POLLUTION, P2-ROUTE-HELPERS-SPLIT
- P2-R3-FOLLOW-UP-1 (V046 enum extension), P2-R3-FOLLOW-UP-3 (exception detail genericization), P2-R3-FOLLOW-UP-5 (V046 byte_size CHECK)
- P3-PYDANTIC-V2-MIGRATE-REPLAY, P3-R3-FOLLOW-UP-4 (PID-reuse create_time identity)
- P0-PROCESS-1 (E4 SOP must include Linux pytest, Python 3.12 parity)

**Sprint B-D pending**：
- B = R4 (UI enable: `/static/tab-paper.html` `subtab-btn-replay` 從 disabled 改 backend-readiness gated) + R5 (real decision/risk replay path: extract pure components + ReplayStrategyAdapter + ReplayRiskAdapter)
- C = R6 (fee/execution calibration: maker/taker fee model + spread/slippage + execution_confidence label none/limited/calibrated) + R7 (MLDE/Dream advisory integration)
- D = R8 (maintenance: cron jobs + healthcheck probes + artifact TTL) + R9 (reality-calibrated usability sign-off final)

---

### REF-20 Gap Closure Plan V1 — Sprint A 啟動（2026-05-04）

**Trigger**：Sprint 4 closure (commit `0ad79f67`) 標記 P6 PRODUCTION CLOSED 後，2026-05-04 Codex production-readiness review 揭 4 個 P0/P1 gap。

**Gaps**：
- **P0-1** `replay_runner` synthetic close-price walker — 不走 IntentProcessor / TickPipeline / exchange / governance，emit `qty=1.0` synthetic long fill，不能驗 strategy/risk parameter delta
- **P0-2** API binary path bug — `route_helpers.py:138/143` 找 `rust/openclaw_engine/target/release/replay_runner`，cargo workspace 實出 `rust/target/release/replay_runner`；同 bug 存於 `helper_scripts/ci/replay_runner_symbol_audit.sh:91`
- **P1-1** UI Replay subtab `aria-disabled="true"` 仍標 "P2 待啟用"
- **G1-G7 additional gaps**：6 個 replay.* 表全 0 rows / `run_state.manifest_id` FK 但無 production manifest registration / `/api/v1/replay/health` 404 / `/manifest/verify` 501 without test key / cron 未裝 / closure 跳過 14d observation / UI copy 仍稱 backend pending

**Plan**：`docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md`（commit `a4ea3571`）

**架構**：9 Wave (R0-R9) + 4 Sprint (A=R1+R2+R3 / B=R4+R5 / C=R6+R7 / D=R8+R9)

**Sprint A scope (2026-05-04 啟動)**：
- R1 Runtime Usability：fix binary path resolution + fix audit script + ensure API env + add `/api/v1/replay/health`
- R2 Manifest Registry：production manifest registration path + atomic `experiments` row + SQL/archive-backed verify + idempotency
- R3 First Real E2E：authenticated minimal replay on Linux + persist 4 表 + verify row count > 0

**Sprint A acceptance**：A1 API spawn runner + A2 DB lineage exists + A3 no dangling FK

**Pre-flight (PM 直查)**：4 個 plan-asserted gap 全證實 (route_helpers + audit script + curl 404 + UI disabled + 6 表 0 row + Linux engine/API alive)

**Wave R0 doc reset**：CLAUDE.md §三/§十 label 改 "closed-with-known-gap (Sprint A in flight)"；TODO.md 加 P1-INFRA-3n/3o/3p/3q 對應 Sprint A/B/C/D。Plan R0 acceptance：plan 檔已 commit `a4ea3571` ✅，Sprint 4 closure entry 完整保留 ✅

**Sprint A 完成前禁止 (plan §11)**：用當前 replay output 判斷策略品質 / 調 live/demo 風控 / 餵 MLDE/Dream 為真實 evidence / 對外宣稱已解決 operator fast backtest pain

---

### REF-20 Sprint 3+4 closure — P6 PRODUCTION CLOSED（2026-05-03 → sync 2026-05-04）

**範圍**：Sprint 3 Track H Decision Lease retrofit AMD-2026-05-02-01 Path A 業務代碼 + V054 audit writer schema/writer + Sprint 3 Track I Linux deploy Phase B-G executed via SSH bridge + Sprint 4 final closure operator override accept conditional skip 14d observation。

**Sprint 3 Track H IMPL（commit `dbcf845b`）**：
- E-1 Rust facade — `governance_core.rs` 951 LOC（`acquire_lease()` / `release_lease()` Path A 兌現 v3 plan）+ `governance_emit.rs` 622 LOC（emission helpers）
- E-2 router gate — `intent_processor/router.rs` +196 LOC（feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` short-circuit 灰度）+ tests +537 LOC
- E-3 Python IPC bridge — `governance_lease_bridge.py` 587 LOC + `lease_ipc_schema.py` 443 LOC + `ipc_client.py` +35 LOC + `governance_hub.py` +240 LOC + sibling tests `test_governance_lease_bridge.py` 758 LOC（44/44 PASS）
- E-4 V054 audit writer — `V054__lease_transitions_audit_writer.sql` 535 LOC（TimescaleDB hypertable + 21-value enum + paired CHECK + FK redirect to V035 governance_audit_log + REF-21 placeholder）+ `lease_transition_writer.rs` 492 LOC
- 配套：`engine_mode_tag_e2e.rs` 211 LOC + `governance_lease_retrofit.rs` 426 LOC + golden_extreme +22 LOC + 三 risk_config*.toml +61 LOC

**Sprint 3 Track I Linux deploy（runbook `7a86d2eb` + Phase B-G executed 2026-05-03 21:30+ via SSH bridge）**：
- Phase A skip（E4 final regression 已跑：3431/1/10 + 3132/2/3 + Track H specific 44/44）
- Phase B V049-V054 6 V### apply：TimescaleDB hypertable + 21-value enum + paired CHECK + FK redirect 全綠
- Phase C cargo --release build：openclaw-engine 28.82s + replay_runner 15.35s = 44s；nm audit 406 symbol / 0 forbidden（0 live_execution / acquire_lease / trading_writer）
- Phase D skip（feature flag default OFF + 回測模塊不需 production maintenance cron）
- Phase E restart_all.sh --rebuild：Engine PID 4122084 + API PID 4122156 + 三模式 paper/demo/live 全 alive + snapshot age 8.1s
- Phase F 5 e2e smoke 核心 3 條 PASS（F.1 401 IDOR auth 修補正常 + F.2 endpoint 真實掛載 + F.5 cron script 真存在）
- Phase G Decision Lease retrofit verify：Track H schema 全綠（lease_transitions hypertable + V051 paired CHECK + V052 FK redirect 全 verified）
- Phase H 14d gradient observation skip（operator override）

**Sprint 4 final closure（commit `0ad79f67`）**：
- Operator override accept：「直接跑掉 A-H，後續有問題再修」（理由：REF-20 是 Paper Replay Lab 回測模塊 + feature flag default OFF + 0 trading.* mutation + 0 live trading 觸發）
- 7 closure item 4 ✅ + 3 ⏭ override skip = **REF-20 P6 CLOSED**
- 24/25 V3 §12 acceptance binding GREEN（#21 ⏸ DEFERRED Wave 7 P5 LG-2/3/4 stable 後解封）
- conditional override 3 條由 operator 後續 action（無時限）：14d observation #4/5/6 + AMD-2026-05-02-01 flag flip canary 24h（~2026-05-15 P0-EDGE-2 後）+ AMD-2026-05-03-01 Wave 7 P5 deploy gate（LG-2/3/4 stable 後）

**Cumulative chain（Sprint 1+2+3+4）**：`2ffe43d` → `edf33c0` → `d602ce0` → `5184990` → `aa9343c` → `ab25a2a` → `db1d04f` → `5c570df` → `c96aed4` → `984ee5d` → `35c0719` → `114f681c` → `dbcf845b` → `7a86d2eb` → `0ad79f67`。

**邊界**：Sprint 3 Track H 業務 runtime + V054 schema + Track I deploy executed；2026-05-04 drift fix（本 entry 所在 commit）為 doc sync only — TODO.md / CLAUDE.md §三 / §十 / 本 changelog / memory 同步至 P6 PRODUCTION CLOSED status。

**Closure doc**：`docs/execution_plan/2026-05-03--ref20_sprint4_final_closure.md`。

### REF-20 Sprint 2 retroactive evidence trail rebuild（2026-05-03）

**範圍**：4 並行 sub-agent（PA Track E + E2 F1 + E4 F2 + R4 G push back）+ PM Track G self-execute。

- **PA Track E** Decision Lease retrofit AMD-2026-05-02-01 partition design：4 task DAG（E-1 Rust facade critical → E-2/E-3/E-4 並行；3.0d work；feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` 灰度 6 Phase rollout 對齊 Wave 7 amendment IMPL/Deploy 2-stage gate）
- **E2 F1** retroactive Wave 3-9 master review：Wave 7 PASS / Wave 3/4/5/6/8/9 CONDITIONAL；10 LOW + 7 P2 ticket 提案
- **E4 F2** retroactive Wave 3-9 cumulative：CONDITIONAL ACCEPT with audit forgery flags；4 P0 forgery（W3 self-introduced doctest + W6 self-introduced flaky + W6 mlde_demo_applier 1542 LOC §九 violation + closure doc「3500+ PASS」虛構數字 cold reality 3387）；3 P2-FOLLOW-UP 提案
- **R4 Track G push back**：採納 R4 read-only audit gate 不應越界寫 doc + P0-4 「false positive vs ✅ DONE」邏輯矛盾，PM 自己接管 Track G doc sync

**正式 amendment**：AMD-2026-05-03-01 Wave 7 P5 IMPL-accept-deploy-blocked（commit `5184990`）。

**Commit chain**：`5184990`（amendment）→ `aa9343c`（Sprint 2 deliverables 4 reports + 3 memory）→ `ab25a2a`（TODO P1-INFRA-3 status correction + 13 P2 ticket）。

**邊界**：本批 docs-only；Sprint 1 commit `edf33c0` 已含業務修補（5 P0 security + 3 schema drift）。

### REF-20 Sprint 1 cold audit fix-up（2026-05-03）

**範圍**：8-agent cold audit verdict NO-GO 後 4 並行 E1 + E2 round 1+2 + E4 regression。

**Commit chain**：`2ffe43d`（P2-AUDIT-7 V044 LOCK TABLE retrofit）→ `edf33c0`（Sprint 1 unified 34 file / 10775 ins / 380 del）→ `d602ce0`（P2-FOLLOW-UP-1/2 E4 pre-existing accept）。

**8-agent cold audit verdict 速覽**：6 NO-GO / 2 CONDITIONAL / 0 GO（PA + E2 + E3 + E4 + CC + MIT + FA + R4 + QA）。19 P0 unique 整合：5 critical security + 3 schema drift + 4 governance + 4 runtime + 2 test + 1 doc。

**Sprint 1 IMPL**：
- Track A — Python `--manifest <path>` 對齊 Rust CLI（解封 IMPL 從未跑過根因 + spawn-then-poll-1.5s + ENVELOPE_KEYS_FOR_SIGNING byte-equal cross-language `ensure_ascii=False`）
- Track B — Rust manifest verify 路徑改用 manifest 自帶 signature/manifest_hash 為 expected（不再 tautology），key.hex 缺失 hard error，加 5 fail-mode unit test + healthcheck `[44]`
- Track C — env var production gate raise + `os.kill` cmdline 校驗 + IDOR `actor_id` filter + Path.resolve 防路徑遍歷 + V053 race-free（BEGIN+LOCK TABLE ACCESS EXCLUSIVE+COMMIT）；replay_routes.py 1603→1494 LOC
- Track D — V049 replay_experiments + V050 replay_simulated_fills + V051 mlde_recommendations 雙路 CHECK + V052 FK redirect + V052_preflight + REF-20_RESERVATION v1.7→v1.9

**驗證**：3387 PASS（+13）/ 1 fail (pre-existing) / 10 skip · 3084 cargo workspace PASS（+7）/ 2 fail (pre-existing E4-P0-2) / 3 ignored · Sprint 1 specific 63/63 PASS · Mac PG 16.13 真 smoke test 4 V### × 2 idempotent → 0 RAISE · 0 跨平台路徑 / 0 hard-boundary mutation / 100% bilingual MODULE_NOTE。

**邊界**：本批 包業務 runtime + DB migration；Sprint 3 deploy 實機 pending operator action。

### REF-20 Wave 1-9 PM autonomous closure（2026-05-03，cold audit 揭結構性 false positive）

**範圍**：PM autonomous mode single session 跑完 Wave 1-9 30 atomic commits + 1 final closure doc，聲稱「24/25 V3 §12 acceptance GREEN」。

**Wave commit chain**：Wave 1 atomic 5 commits → Wave 2 `1851714` + `b1f6b8a` → Wave 3 `5a618ff` (含 P2a-S3-S6 + P2b-S7-S10 + closure) → Wave 4 `4b48b6d` (single 26 file 7360 ins) → Wave 5 `457a458` (13 task NumPyro 2320 LOC) → Wave 6 `eb5f106` (P4 advisory 8 task) → Wave 7 `c887e4e` (operator override hard prereq bypass) + `53ab7e7` (defer note + master closure) → Wave 8 `8429af1` (typed-confirm + V044) → Wave 9 `1f5d019` (KPI + V047/V048) → final closure `5a7581e`。

**cold audit 結論**：24/25 GREEN 是「結構性 false positive」— runner 從未啟動 → #2/#10/#14/#19 都是 vacuous truth；Linux runtime 0 行 active；Wave 4-9 跳過 §八 強制工作鏈 E2+E4 review；Decision Lease retrofit (P0-GOV-1) 未做但 Wave 8 P6 聲稱 closed；3 V### schema 規範表全缺。

**邊界**：Wave 1-9 業務 runtime + frontend + V### migration + cron land in tree，**deploy gate retained**。

### REF-20 Paper Replay Lab dev plan V2.1 Round3（2026-05-02）

**範圍**：審閱並納入 `docs/execution_plan/2026-05-02--ref20_v2_round3_audit.md`，新增 `docs/execution_plan/2026-05-02--ref20_paper_replay_lab_dev_plan_v2_1_round3.md` 與 dedicated UX subdoc `docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md`，並更新 `docs/execution_plan/README.md` / `docs/README.md`。

**決策**：Round3 大多成立，但不推翻 V2；V2.1 將 schema 物理欄位、MLDE retrofit、DB role guard、PM V### reservation + Guard A/B/C、5 策略 indicator leak-free sweep、dedicated `replay_runner`、P2 fail-closed isolation、Mac non-actionable smoke policy、manifest TTL/quota、UX subdoc gate 收斂成 P0/P1/P2 可執行 contract。同時保留 V2 的核心判斷：P2 可以使用 `TickPipeline` / `IntentProcessor`，但必須在 isolated no-write replay profile 下運行。

**邊界**：本批 docs-only；未改 runtime、DB migration、策略、風控或 live/demo 配置。V2.1 Round3 是當前 implementation-planning baseline，runtime implementation 仍需 REF-19/REF-20 v2 amendment、migration reservation、UX sign-off 與 P2a schema/auth/signature contracts。

### REF-20 Paper Replay Lab dev plan V2（2026-05-02）

**範圍**：審閱 `docs/execution_plan/2026-05-02--ref20_v1_round2_audit.md`，新增 `docs/execution_plan/2026-05-02--ref20_paper_replay_lab_dev_plan_v2.md`，並更新 `docs/execution_plan/README.md` / `docs/README.md`。

**決策**：Round2 大多成立，V2 採納 `evidence_source_tier` DDL CHECK、`replay.simulated_fills`、獨立 replay HMAC key、route auth/concurrency、硬量化閾值、P1 UX contract、P3+ canonical runner 等要求；明確反對兩個過度條款：P2 不應禁 `TickPipeline` / `IntentProcessor`，Mac smoke 不應禁 S2 public market data。正確邊界是 P2 no-write isolated replay + Mac 禁 S0/S1/private fills。

**邊界**：本批 docs-only；未改 runtime、DB migration、策略、風控或 live/demo 配置。V2 是當前 implementation planning baseline，runtime implementation 仍需 REF-19/REF-20 v2 amendment 與 P2a schema/auth/signature contracts。

### REF-20 Paper Replay Lab dev plan V1（2026-05-02）

**範圍**：審閱並保留 `docs/execution_plan/2026-05-02--ref20_paper_replay_lab_dev_plan_draft_v0.1.md`，確認多數改進建議屬真實風險；新增 `docs/execution_plan/2026-05-02--ref20_paper_replay_lab_dev_plan_v1.md`，並同步更新 `docs/execution_plan/README.md` 與 `docs/README.md`。

**決策**：V1 採納 manifest HMAC、replay route auth、replay registry、MLDE row-level evidence source guard、execution calibration OOS / sample-power / selection-bias gate、resource isolation、Paper/Learning/Agents Monitor 邊界等要求；修正 draft v0.1 的過度阻塞：P2 read-only S2/S3 smoke replay 不必等 Decision Lease retrofit，但任何 calibration/advisory/demo handoff 均需後續 guard。

**邊界**：本批 docs-only；未改 runtime、DB migration、策略、風控或 live/demo 配置。V1 是 implementation baseline，不代表可跳過 REF-19/REF-20 v2 amendment。

### REF-20 Paper Replay Lab + Learning surface design（2026-05-02）

**範圍**：新增 `docs/references/2026-05-02--paper_replay_learning_surface_design.md` 與中文 companion `docs/references/2026-05-02--paper_replay_learning_surface_design_zh.md`；同步更新 `docs/governance_dev/SPECIFICATION_REGISTER.md` 與 `docs/README.md`。

**決策**：Paper Tab 原地升級為 Paper Replay Lab，保留 current paper session 並新增 fast replay / run compare / candidate handoff；Learning 保持 durable learning cockpit，新增 replay evidence inbox 與 ML/Dream producer monitor；目前嵌在 Learning 的 5-Agent 面板應抽出為 read-only Agents Monitor，功能保留不刪除。

**邊界**：REF-20 延續 REF-19：Replay 可調用 MLDE / DreamEngine，但不將其改寫為 replay-only；Replay outputs 僅作 source-tagged evidence 或 advisory recommendation，不直接寫 `trading.fills`、不混入 `learning.mlde_edge_training_rows`、不直接修改 live / live_demo。

### REF-19 中文 companion + 三段同步（2026-05-02）

**範圍**：新增 `docs/references/2026-05-02--reality_calibrated_fast_replay_governance_zh.md`，作為 REF-19 中文 companion；同步更新 `docs/governance_dev/SPECIFICATION_REGISTER.md` 與 `docs/README.md`。

**決策**：中文版與英文版同義，不覆蓋英文契約。日常討論與後續實作可引用中文版，但治理邊界維持一致：Replay 調用 MLDE / DreamEngine 作實驗環境與資料來源之一，不將它們改造成 replay-only 工具。

**同步**：此批為 docs-only，完成 Mac local → origin/main → Linux `trade-core` ff-only pull 三段同步；未 rebuild / restart / DB write / strategy/risk config mutation。

### REF-19 Reality-Calibrated Fast Replay governance（2026-05-02）

**範圍**：新增 `docs/references/2026-05-02--reality_calibrated_fast_replay_governance.md`，並在 `docs/governance_dev/SPECIFICATION_REGISTER.md` / `docs/README.md` 補登 REF-19。

**決策**：Reality-Calibrated Fast Replay 定位為高壓縮歷史實驗環境與資料來源；可調用 MLDE / DreamEngine / OpportunityTracker，但不得把它們改造成 replay-only 工具。ML/Dream 本職仍是 Agent 自我學習、策略修復、風控/參數調整與候選提案。

**邊界**：Replay 只能產生 `reject` / `defer_*` / `demo_candidate` / `live_candidate_research_only` 等研究或候選 verdict，永不產生 `live_approved`；synthetic / calibrated replay rows 必須 source-tagged，且不得混入 real fill labels；live/live_demo mutation 仍需 GovernanceHub + Decision Lease + live gates。

### TODO Follow-through 1-4（2026-04-30）

**範圍**：完成 operator 要求的四項 TODO follow-through：active docs runtime drift 校正、G1-04 fee/R:R as-of compute、G8-01 cognitive adaptive test/coverage closure、ML training data hygiene quantification。

**結果**：runtime checkpoint 記錄校正為 code-bearing `a9fce24` + latest passive healthcheck SUMMARY WARN；G1-04 post-reload slice n=665 / maker_like 73.23% / fee_drop 59.32%，但 R:R mixed 且 ma_reverse_cross 仍 net negative；G8-01 targeted pytest 40/0，`CognitiveModulator` stdlib trace/AST coverage 76/81 (93.8%)；ML hygiene dust spiral noise 37/1843 = 2.01%，24h recurrence 0，無需 DB backfill。

**邊界**：純文檔與 read-only analysis；未改 trading/risk/strategy 參數，未 rebuild/restart，未 DB write，未放寬 live authorization。G2-01 acceptance 仍等 2026-05-07/08。

**報告**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-30--todo_followthrough_g1_g8_mlhygiene.md`。

### Dust / Edge / Scout follow-through（2026-04-30 · commit `f8a245c`）

**範圍**：完成 operator 指定的三項 follow-through：dust residual runtime proof、post-deploy edge cutoff observation、Scout heartbeat production caller wiring。

**Dust proof**：Linux runtime 載入後，DB 觀察到 8 筆 Demo/LiveDemo `qty=0` close order 皆 join 到 nonzero fill；Demo `APEUSDT` 與 LiveDemo `XAGUSDT` `orphan_frozen` close path 已證明 Bybit full-position close form 可用。

**Edge cutoff**：以 2026-04-30 21:10 CEST 為 cutoff；`[33]` n=15 maker_like 40.0% / fee_drop 39.0%；`[38]` lifecycle n=1+1 insufficient；`[40]` rows=0。結論是繼續 cutoff observation，不用混舊 rolling window 決策。

**Scout heartbeat**：`strategy_wiring_scanner._scan_and_produce_intel()` 在 empty scan 與 successful intel scan 都呼叫 `ScoutAgent.record_scan()`，補上 production ScoutWorker caller。新增 hermetic pytest 2 cases。

**驗證 / runtime**：`test_strategy_wiring_scanner.py` 2/0、`test_agent_heartbeat_contract.py` 36/0、targeted `py_compile` PASS、`git diff --check` PASS。Linux API-only reload applied Scout Python wiring (uvicorn PID `1591455`); Rust engine PID `1529433` stayed alive and watchdog remained `engine_alive=true`.

### P1-11 BB-BREAKOUT/REVERSION-DORMANT-1 全工 + 多輪 audit 收尾（2026-04-24 · commits `0528d96`/`38a14ca`/`148bd96`/`bcc5401`/`63957ad`/`3b483a3`/`c8a2a2c`/`69ea580` 等）

**範圍**：P1-11 (2)+(3) Rust 落地 + (1) Phase 1 Python 信號級 sweep + 多輪 self-audit + QC/MIT/PM/PA/FA multi-role 並行 audit 收尾。

**(2) DonchianMode enum** — Donchian AND→Score/Off 三模式（`DonchianMode::{Hard, Score, Off}`）；Hard 預設 bit-identical 基線；Score breach=+`donchian_score_bonus`(默認 0.15)/miss=扣同量；Off 跳過 Donchian；validate `[0.0, 0.5]` + 熱重載 + 14 unit tests。

**(3) BbBreakoutProfile enum** — A/B preset variant（Conservative/Balanced/Aggressive）+ `BbBreakoutParams::for_profile()` helper；`Balanced == default()` 測試固化；3 variant 全通過 validate（注：種子值在 1m bandwidth 分佈下皆不可觸發，Phase 2 需 rescale）。

**(1) Phase 1 Python sweep** — `helper_scripts/research/bb_breakout_threshold_sweep.py` 信號級閾值 sensitivity sweep（5 symbols × 14d × 64 combos pooled）；首版 commit `148bd96` 後經 first selfaudit 修 3 bug（F1 wording / F2 stats / B3 FIX-26 parity 錯）+ 多角色 audit 修 5 FAIL + 6 WARN（mod.rs:492 saturating_add 對稱 / Python ddof=1 + df-aware t_crit + Bonferroni / cluster-SE / leak-free Donchian shift(1) / +4 boundary tests / [12] healthcheck）。

**F4 Rust bug FIX-26-DEADLOCK-1**（commit `bcc5401`）— self-audit 修 Python sweep 對齊 Rust FIX-26 語義時，發現 Rust `bb_breakout::on_tick` 中 `squeeze_detected_ms` 過期後**無清除路徑**（只有入場 mod.rs:636 設 None；on_external_close 明示 preserve；無其他 clear）。後果：若首次 squeeze 45min 窗口內無入場（任何 expansion/vol/%B/Donchian gate 失敗），該 symbol **永久 dormant**。是 bb_breakout 14d 0 fills 的**第一層真正根因**（threshold 不對是第二層）。修：is_none() guard 前加 expiry-based auto-clear；commit `63957ad` 同時補 line 492 entry path saturating_add 對稱；3 + 4 = 7 個 regression test（含 overflow / expiry=0 / exact-boundary / on_external_close interaction）。

**Findings 最終判決**：
- F1 1m scale mismatch CONFIRMED（squeeze_bw=0.03 在 1m BB bandwidth 100% 觸發；expansion_bw=0.04 永不達成；q=0.99 僅 0.014）
- F2 「signals ≠ edge」方向觀察 PASS / 「top edge」claim FAIL（56 qualified combo 沒一個達 naive |t|>1.96）
- **F3 RETRACT** — 原「Donchian breach 反向關聯 fwd30 -3.20 顯著」是 measurement bias artifact（`rolling(N).max()` 含 current bar → breach=「current bar 是 N-bar max」必然 mean-revert）；leak-free shift(1) Donchian 下 effect 消失（-0.45/+0.34）。`DonchianMode::Score` 方向現無證據判定錯。
- F4 FIX-26-DEADLOCK-1 deterministic 邏輯 bug，已修 + 測試固化

**Healthcheck [12] `bb_breakout_post_deadlock_fix`**（commit `c8a2a2c`）— §七「被動等待 TODO 必附 healthcheck」硬規則合規。bb_breakout 7d entries 數三態：0=FAIL（fix 沒生效或閾值還錯）/ 1-5=WARN / ≥6=PASS。

**測試**：bb_breakout 模組 42 → 56 → 59 → **63 passed / 0 failed**；engine lib 1939 → **1980 passed / 0 failed**（+41）。Mac + Linux release 均驗。

**部署**：所有 commits 已 push origin main。**待 operator 下次 `restart_all.sh --rebuild`** 部署 FIX-26-DEADLOCK-1；部署後 [12] healthcheck cron 6h 自動報 fill 復活。

**Phase 2 backlog**（priority sorted in TODO §P1-11）：F3 leak-free 大樣本 / fee model / persistence+cooldown sim / profile rescale / timeframe assert / bb_reversion 同構改造。

**報告**：`.claude_reports/20260424_024807_p1_11_qcmitpmpafa_audit_closeout.md` (audit 全細節)。

---

### TICK-PIPELINE-MOD-SPLIT-1 — tick_pipeline/mod.rs 拆 3 檔進 §七 1200 硬上限（2026-04-22 · commit `3d67a99`）

**觸發**：ON-TICK-SPLIT-1（`bfedb56` 2026-04-21）後 `tick_pipeline/mod.rs` 仍 2274 行違反 §七 1200 行硬上限；`impl TickPipeline` 巨塊 L906-2178 ~1272 行（ctor/config sync/exit helpers/channel setters 交織）。原列 P3 backlog `TICK-PIPELINE-MOD-SPLIT-1` ~2-3d；收尾 Step 0 衍生章節前最後一項。

**執行**：sub-agent（`general-purpose`）機械 split，~14 分鐘 70 tool uses 完成。

**範圍**：把唯一的 `impl TickPipeline { ... }` 塊拆成 3 個 sibling child-module 檔（每檔一個 `impl super::TickPipeline { ... }`），按語意分組：

| 新檔 | LOC | 內容 |
|---|---|---|
| `pipeline_ctor.rs` | 422 | `new` / `with_balance` / `with_kind` + 20+ 基本 setters/getters（endpoint / symbol_registry / edge_estimates / linucb / predictor / shadow_fill_tx / decision_feature_tx / exit_feature_tx / price_tracker / rng_seed / edge_predictor_store / risk_store 等） |
| `pipeline_config.rs` | 300 | `set_news_snapshot` / `set_risk_store` + `apply_risk_snapshot` / `set_budget_store` / `sync_risk_config_if_changed` / `set_maker_kpi_store` + `sync_maker_kpi_config_if_changed` / `current_cost_edge_max_ratio` / `current_min_profit_to_close_pct` / `set_fee_rate` / `set_account_manager` |
| `pipeline_helpers.rs` | 654 | `close_position_at_symbol_market` / `emit_close_fill` / `try_emit_exit_feature_row` + `build_exit_feature_row` / `should_persist_signal` / `derive_regime` / `set_instrument_cache` / `set_stop_channel` / `set_shadow_channel` / `clear_pending_close` / `clear_all_pending_close` / `set_*_channel` × 4 / `retriage_synthetic_owner_for_symbol` |

mod.rs 保留 types/struct/enum-impls/free-fns（`parse_exit_tag` / `snapshot_to_input`）+ mod decls；**1012 行**（降 55.5%，進 1200 硬上限）。3 新檔皆 under 800 soft warn。

**Visibility 升級**：8 個被 on_tick/ 跨檔呼的私有 fn 從 `fn` 升 `pub(super) fn`：
- pipeline_config：`sync_risk_config_if_changed`（step_0_fast_track） · `sync_maker_kpi_config_if_changed`（step_0_fast_track） · `current_cost_edge_max_ratio`（step_6_risk_checks） · `current_min_profit_to_close_pct`（step_6_risk_checks）
- pipeline_helpers：`close_position_at_symbol_market`（step_0_5 / step_0_fast_track / step_3 / step_4_5 / step_6） · `emit_close_fill`（同 set） · `should_persist_signal`（step_3_signals） · `derive_regime`（step_6_risk_checks）

保持私有（同檔內 caller）：`apply_risk_snapshot`（`set_risk_store` 呼） · `build_exit_feature_row`（`try_emit_exit_feature_row` 呼）。

**驗證**：
- Mac debug `cargo test -p openclaw_engine --lib`: **1835 passed / 0 failed**（與 pre-split 同 baseline，純 refactor）
- Linux release `ssh trade-core ... cargo test --release`: **1835 passed / 0 failed**（0.52s）
- `cargo check -p openclaw_engine --lib`：clean，6 warnings 皆 pre-existing
- 所有檔 under 1200 hard cap（mod.rs 1012 / pipeline_ctor 422 / pipeline_config 300 / pipeline_helpers 654）

**Workflow**：主 session 讀 mod.rs 邊界 + 決定 3-way split 分組 + 撰 sub-agent spec（method 逐個列、visibility 升級規則、檔案 skeleton 模板、driver 驗證步驟、禁止清單）→ Agent tool 派 `general-purpose` sub-agent → sub-agent 完成 14 分鐘 → 主 session 驗 wc + cargo test → 寫 `.claude_reports/20260422_204237_tick_pipeline_mod_split.md` → commit + push。

**檔案**（1 commit, 4 files）：
- `3d67a99` — `tick_pipeline/mod.rs` +11/−1273 · `tick_pipeline/pipeline_ctor.rs` +422（新）· `tick_pipeline/pipeline_config.rs` +300（新）· `tick_pipeline/pipeline_helpers.rs` +654（新）
- 淨 LOC +114（純結構分檔，零邏輯改動）

**Governance**：
- §七 file size：mod.rs 2274 → 1012（under 1200 hard cap，降 55.5%）；3 新檔最大 654（pipeline_helpers，under 800 soft warn）
- §七 bilingual：3 新檔頂 MODULE_NOTE 中英對照
- feedback_subagent_first：典型機械 refactor 案例，主 session 專注 spec 設計 + 驗收，執行力卸載
- Step 0 衍生新 TODO 章節 5/5 ✅ 於本 commit 收尾 — 歸檔 `docs/archive/2026-04-22--step_0_derived_todo_batch.md`

---

### TRACK-P-V2-SWAP-1 — Priority 6 v1 linear → v2 non-linear + ExitConfig（2026-04-22 · commit `306993e`）

**觸發**：2026-04-21 晚 3 TRACK-P-T4-WIRING-1（`e95c779`）接上 `ExitFeatures` builder 後，Priority 6 仍呼 v1 `physical_micro_profit_lock` + 線性 `PhysLockConfig`（`giveback_atr_norm_threshold=0.7` 固定閾值）。v2 non-linear pure fn + `ExitConfig`（threshold = max(base − slope × peak_atr_norm, floor)）在 `aee96b9` + 31 單測綠，但 runtime 未接。本次解除此 dual-track 殘留。

**範圍**：
1. `config/risk_config.rs`：field `phys_lock: PhysLockConfig` → `exit: ExitConfig`（`#[serde(alias = "phys_lock")]` 保 TOML 相容 — 當前三環境 `risk_config*.toml` 均無此 section 全走 Default，alias 為保險）；`use crate::exit_features::ExitConfig` 新增；validate 掛 `self.exit.validate().map_err(|e| format!("risk.exit: {}", e))?`；EOF `PhysLockConfig` struct + 5 default fn + `Default` + `validate` impl 共 ~94 行整塊退役（留一段雙語 retire comment 作為 grep anchor）
2. `risk_checks.rs`：import 改 `use crate::exit_features::{physical_micro_profit_lock_v2, ExitFeatures, PhysicalDecision}`；Priority 6 call site 從 `physical_micro_profit_lock(features, &config.phys_lock)` 改為 `physical_micro_profit_lock_v2(features, &config.exit)`；本檔 v1 `physical_micro_profit_lock` pure fn（~50 行）+ 8 個 v1 直接單測（~135 行）全刪（v2 在 `exit_features/v2.rs` 已有 25 等值單測）
3. 保留 4 個 end-to-end 整合測試經 `check_position_on_tick` exercise Priority 6（v2 boundary `<=` / `>=` 較 v1 `<` / `>` 更保守，既有輸入全通過）

**v2 vs v1 runtime 差異**（部署後可觀察）：

| 維度 | v1 linear | v2 non-linear | 觀察點 |
|---|---|---|---|
| Gate 1 邊界 | `edge < floor` → Hold | `edge <= floor` → Hold | edge 剛好等於 floor 的 position 會被擋更久（保守） |
| Gate 4a giveback 閾值 | 固定 `0.7` | `max(1.0 − 0.15 × peak_atr_norm, 0.3)` | 高 peak 倉鎖得更快（peak_atr_norm=5 → 閾值 0.3 vs v1 0.7）；淺 peak 倉鎖得更慢（peak_atr_norm=0 → 閾值 1.0 vs v1 0.7） |
| Gate 4b 陳舊邊界 | `dt > stale_peak_ms` | `dt >= stale_peak_ms` | 剛滿時間窗且 ROC 負的 position 會被鎖（v1 要嚴格超過） |

整體方向符合 DUAL-TRACK-EXIT-1 §三 L108-111 設計意圖「防微利即套離場、追求最高單筆 close 盈利」。

**Reason-string ABI 不變**：v2 也 emit `phys_lock_gate4_giveback` / `phys_lock_gate4_stale_roc_neg`，下游 `strip_phys_lock_prefix` + `parse_exit_tag` 零改。歷史 `phys_lock_gate1_low_edge` tag（v1 反轉前）由下游解析層向後相容。

**驗證**：
- Mac debug `cargo test -p openclaw_engine --lib`: 1843 → **1835 passed / 0 failed**（−8 = 退役 8 個 v1 直測：gate1_low_edge_holds / gate1_pass_with_sufficient_edge / gate2_holds_within_min_hold_secs / gate3_holds_when_peak_below_atr_threshold / gate4_giveback_triggers_lock / gate4_stale_peak_with_negative_roc_locks / holds_on_missing_atr_conservative / reason_string_format_stable；精確對帳）
- Linux release `ssh trade-core ... cargo test --release`: **1835 passed / 0 failed**（0.52s）
- Mac + Linux 完全對齊，無平台分歧

**Workflow**：Mac CC 本地開發 → `cargo check` + `cargo test` 綠 → 寫 `.claude_reports/20260422_200623_track_p_v2_swap.md` → commit → operator 明確授權本 session 後續直接 push → push origin main → `ssh trade-core "git pull --ff-only && cargo test --release"` 驗 Linux release 同綠。第一次 commit 時 push 被 permission hook 擋（理由：本次 prompt 無 explicit push 授權）— operator 放行後順利推送，已納入 §七「commit 即 push」硬規則。

**檔案**（1 commit, 2 files）：
- `306993e` — `rust/openclaw_engine/src/config/risk_config.rs` +23/−96 · `rust/openclaw_engine/src/risk_checks.rs` +31/−218（淨 LOC −260）

**Governance**：
- §七 file size：`risk_config.rs` 1402 → ~1306（硬上限 1200 以下再緩衝 96 行）；`risk_checks.rs` 1062 → ~884（硬上限 1200 以下）
- §七 bilingual：所有新增 comment 皆中英對照（field doc / retire block / integration-test note）
- feedback_no_dead_params：v1 pure fn + `PhysLockConfig` swap 後即為死碼，故整塊退役（不保留 dual-track）
- feedback_env_config_independence：三環境 `risk_config*.toml` 未動，`#[serde(alias)]` 保未來手寫相容
- ARCH-RC1 / 3E-ARCH：`RiskConfig` 保持 `Arc<ArcSwap<RiskConfig>>` 熱重載語意不變，`ExitConfig` 走同一 ArcSwap 快照

**部署**：operator 指示先不部署；engine PID 3954769 仍跑 v1 linear。下次 `ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --rebuild"` 後 v2 non-linear giveback 即時 fire。部署後建議 24h 看 `trading.fills.exit_reason LIKE 'risk_close:phys_lock_gate4_%'` 分布與 v1 歷史對比（v1 部署期 = 2026-04-21 20:44 ~ 下次 `--rebuild`，短窗但可做樣本參考）。

**Memory 更新**：`project_track_p_runtime_dead.md` supersede 為 `project_track_p_runtime_live.md`（runtime 接線層面已 live、v2 swap 代碼層面也 live，僅部署未執行）。

### CANARY-WRITER-ENV-RACE-1 + TICK-PIPELINE-MOD-UNUSED-IMPORTS-1 — 並行派發清尾（2026-04-21 · commits `d454c17` + `c164cb6`）

**觸發**：ON-TICK-SPLIT-1 sub-agent 回報兩個 pre-existing 問題，operator 指示並行派發兩個 sub-agent 清：

1. **CANARY-WRITER-ENV-RACE-1** (`d454c17`)：`canary_writer::tests::{spawn_honours_disable_dump, spawn_without_canary_mode_is_disabled}` 並行跑偶發 flake。套 AI-SERVICE-CLIENT-ENV-RACE-1 (`580304a`) 同一 pure-fn pattern：
   - 抽 `decide_canary_enable_from(canary_mode: Option<&str>, disable_dump: Option<&str>) -> CanaryEnableDecision`（3-variant enum `Enabled` / `DisabledByMode` / `DisabledByKillSwitch`；3-variant 而非 bool 為保留原 silent-disable vs `info!` log 雙語意）
   - `spawn()` 改為薄 wrapper 讀 env → 轉呼 pure fn → match 3 variant 保留 fall-through 行為
   - 移除 2 env-racy 測試，新增 5 decision 測試（`decide_honours_disable_dump` / `decide_without_canary_mode_is_disabled` / `decide_canary_mode_only_enables` / `decide_kill_switch_requires_canary_mode_first` / `decide_non_one_canary_mode_values_are_disabled`）；7 → 10 tests（net +3）
   - `canary_writer.rs` 454 → 569 行（仍 ≤ 800 soft cap）
   - 2× parallel `cargo test` 清無 flake
   - 加 `CANARY-WRITER-ENV-RACE-1 (2026-04-21)` 雙語 explanatory block 於 test module 頂部，鏡像 `580304a` 模板

2. **TICK-PIPELINE-MOD-UNUSED-IMPORTS-1** (`c164cb6`)：ON-TICK-SPLIT-1 (`bfedb56`) 後 `tick_pipeline/mod.rs` 暴露 3 個 unused-import warnings（`RiskAction` / `Instant` / `debug`）。Option A（最乾淨）清法：
   - 刪 `tick_pipeline/mod.rs` L14 `use crate::risk_checks::RiskAction;`（step_6_risk_checks.rs:36 已有直接 use）
   - 刪 L27 `use std::time::Instant;`（5 個 step 檔 + on_tick/mod.rs 皆已有直接 use）
   - L28 `use tracing::{debug, info, warn};` → `use tracing::{info, warn};`（僅移除 `debug`；step_0_5_h0_gate + step_3_signals 已直接 use，其他 callers 走 FQ macro path）
   - **無 step 檔變動** — ON-TICK-SPLIT-1 拆分時就已將必要 imports 安置於各 step 檔；本次純屬 mod.rs 的殭屍 use 清除

**驗證**（合併後）：
- Mac debug `cargo test -p openclaw_engine --lib`: 1840 → **1843 passed / 0 failed**（+3 from canary_writer；tick_pipeline-mod-unused 為零語意改動）
- Linux release `ssh trade-core ... cargo test --release`: 1843 passed / 0 failed
- `cargo build -p openclaw_engine` warning count: 13 → **10**（-3 對齊 unused-imports 清除；零新 warning）
- 2× parallel full-lib 跑皆清，CANARY-WRITER flake 根除

**Workflow**：單一 Agent tool-use block 同時發兩個 sub-agent 並行（per system prompt 「並行」指示）。Task A (canary_writer) ~3min scope + Task B (mod.rs imports) ~2min scope，後者更快但兩者非同步完成通知。兩個 sub-agent 被明確指示不 commit/不 push，主 session 收到兩個完成通知後先跑合併測試驗證再分別 commit（A 先 B 後，利 bisect）。

**檔案**（2 commits, 2 files）：
- `d454c17` — `rust/openclaw_engine/src/canary_writer.rs` +144/-29
- `c164cb6` — `rust/openclaw_engine/src/tick_pipeline/mod.rs` +1/-3

**Governance**：
- §七 file size：canary_writer 569 ≤ 800；mod.rs 2273 仍超 1200 hard cap（legacy bloat，`TICK-PIPELINE-MOD-SPLIT-1` P3 另案處理）
- §七 bilingual：兩 commit 新加 comments 皆中英
- feedback_subagent_first：典型小 scope 並行派發案例（非編碼決策、機械性 refactor）

**後續 TODO**（本 entry 內衍生）：
- `TICK-PIPELINE-MOD-SPLIT-1`（P3，~2-3d）：`tick_pipeline/mod.rs` 2273 行超 1200 hard cap，結構上比 on_tick.rs 難拆（涉及 `TickPipeline` struct 定義 + 多 impl block 分散）。不阻塞但列為尾巴。

---

### ON-TICK-SPLIT-1 — `tick_pipeline/on_tick.rs` 2071 行拆為 8 檔目錄（2026-04-21 · commit `bfedb56` · sub-agent 並行派發）

**觸發**：EXIT-FEATURES-SPLIT-1 報告 §6 flag 的 follow-up；operator 指示「並行派發 sub-agent 做 ON-TICK-RS-SPLIT-1，同時主 session 做 AI-SERVICE-CLIENT-ENV-RACE-1」。Sub-agent 工時 ~15min（general-purpose agent 在背景跑，主 session 並行做 env-race fix）。

**拆分結構**：

```text
rust/openclaw_engine/src/tick_pipeline/on_tick/
├── mod.rs                           157 行  # orchestrator: impl TickPipeline::on_tick
│                                            #   threads owned state via
│                                            #   ControlFlow<Break=early-return, Continue=state>
├── helpers.rs                       152 行  # strip/log PHYS-LOCK pub(crate) helpers
│                                            #   + T4-FIX 端到端測試
├── step_0_fast_track.rs             516 行  # prelude（熱重載/stats/ADL/市場事件）
│                                            #   + Step 0 halt/halve/close-all
├── step_0_5_h0_gate.rs               93 行  # H0 門控 shadow/硬阻斷
├── step_1_2_klines_indicators.rs    111 行  # kline 聚合 + 指標 + FeatureSnapshot
├── step_3_signals.rs                192 行  # pause gate + boot cooldown + 信號評估
├── step_4_5_dispatch.rs             929 行  # 策略分派 + intent + maker sweep + 策略平倉
└── step_6_risk_checks.rs            359 行  # 9-check + halt/cooldown 派發 + T4 closure
```

- **mod.rs**：Track P 文檔 + borrow-check surface doctrine 中英雙語；6 個 step 以 `ControlFlow` 早退 + owned return value 串接：`ft_pause_new_entries` (step_0 → step_4_5) / `h0_allowed` (step_0_5 → step_4_5) / `Option<IndicatorSnapshot>` (step_1_2 → step_3/4_5/tail canary) / `Vec<Signal>` (step_3 → step_4_5/tail canary) / `Vec<OrderIntent>` (step_4_5 → tail canary)。`pub(crate) use helpers::…` 保 `crate::tick_pipeline::on_tick::strip_phys_lock_prefix` 等路徑相容。
- **step_4_5_dispatch.rs** 929 行超 800 soft warn：sub-agent 記錄「`self.orchestrator.strategies_mut()` 迭代借用必須與 `intent_processor/paper_state/recent_intents/exchange_seq/...` disjoint field 存取共存於 **單一 fn**，NLL 限制無法再拆；強拆會 force `clone/RefCell/field-layout` 改動，違反零語意變更」。<1200 hard cap 可接受，doctrine 在 mod.rs header 記錄。
- **step_6_risk_checks.rs**：T4 `exit_features_fn` closure（commit `e95c779`）含 3 sub-borrow (`paper_state_ref / price_tracker_ref / edge_estimates_ref`) + `build_exit_features_for_tick` 呼叫完整保留，**不得**跨 step 拆。

**外部呼叫零改動**：`tick_pipeline/mod.rs` 的 `mod on_tick;` 自動解析為 `on_tick/mod.rs`（Rust 模組 tree 規則）。`tick_pipeline::on_tick::strip_phys_lock_prefix` 等 pub(crate) 路徑透過 `pub use helpers::…` 保持穩定。grep 無 external caller 直接進入這些 helper（只 `risk_checks.rs:235` 的 comment 提及）。

**Tests**：engine lib **1840 passed / 0 failed**（Mac debug `--test-threads=1` + 預設 parallel + Linux release 均驗）。Sub-agent 單次 parallel 跑見 `canary_writer::tests::spawn_honours_disable_dump` 偶發 fail，驗證為 pre-existing env-var race（與本 refactor 無關），列為 `CANARY-WRITER-ENV-RACE-1` (P4) 候補 TODO 套同一 pure-fn pattern 清。

**Workflow**：並行派發策略 — 主 session 做小 scope env-race fix（commit `580304a`，先 push），sub-agent 跑背景做大 scope split。兩個 task 檔案不重疊（ai_service_client.rs vs tick_pipeline/），零 git race。Sub-agent 遵守「不 commit 不 push」指令，dirty tree 交回主 session 審 + commit。Full test 驗 1840 綠後才 commit。

**檔案變更**（9 changed — `git rm` 1 + create 8 = net +8，total +2,509/-2,071）。

**Governance**：
- §七 file size：7/8 檔 ≤ 800 soft warn；step_4_5 929 超 soft 但 doctrine documented ≤ hard cap
- §七 bilingual：all 8 files 中英 module headers
- 根原則 #10 認知誠實：sub-agent 明確標示 deviation（step_4_5 為何未拆）+ pre-existing flaky test 與本 PR 無關

**後續 TODO**（本 changelog entry 內衍生）：
- `CANARY-WRITER-ENV-RACE-1` (P4, ~30min)：`canary_writer::tests::spawn_honours_disable_dump` 並行 flake，套 `resolve_socket_path_from` pure-fn pattern 修
- `TICK-PIPELINE-MOD-SPLIT-1` (P3, ~2-3d)：`tick_pipeline/mod.rs` 本身 2276 行也超 §七 hard cap，另案處理（結構上比 on_tick.rs 更難拆，涉及 `TickPipeline` struct def + impl 的跨 trait 組織）

---

### AI-SERVICE-CLIENT-ENV-RACE-1 — env-var test flake 根除（2026-04-21 · commit `580304a`）

**觸發**：EXIT-FEATURES-SPLIT-1 報告 §5 flag。`ai_service_client::tests::{test_default_socket_path, test_env_override_socket_path, test_data_dir_fallback}` 三測試 `std::env::set_var/remove_var` `OPENCLAW_AI_SERVICE_SOCKET` + `OPENCLAW_DATA_DIR` 與並行測試競爭同 key；Mac 本地 `$OPENCLAW_DATA_DIR` 有值時 ~1/1839 run 偶發 fail。

**修復**：抽 pure fn `resolve_socket_path_from(sock: Option<&str>, data_dir: Option<&str>) -> PathBuf` 承接優先序邏輯（sock 覆寫 > data_dir + 預設名 > hard-coded default）；舊 `resolve_socket_path()` 改為薄包裝讀 env 後 forward。3 race 測試改呼 pure fn + 直接注入 `Option<&str>`，完全不動 env = 零 race 可能。

**新測試**：`test_sock_override_beats_data_dir`（顯式斷言 sock 覆寫 > data_dir 優先序；舊測試透過 env 組合隱含假設，新測試提升為 first-class assertion）。

**Tests**：`cargo test -p openclaw_engine --lib ai_service_client::tests` 9 passed / 0 failed（原 8 + 新加 1）。engine lib baseline 1839 → **1840**（+1 新測試）。

**Workflow**：與 ON-TICK-SPLIT-1 並行派發。主 session 3 min 完成 + 先 push，避免等 sub-agent 完成才合併；commit 順序 `580304a` (env-race) → `bfedb56` (on_tick split)，兩者檔案不重疊。

**檔案**（1 changed, +59/-45）：
- `rust/openclaw_engine/src/ai_service_client.rs`

**Governance**：修復僅測試層。Production `resolve_socket_path()` wrapper 仍讀 env — 單執行緒啟動時讀，無 race，不需改。

---

### EXIT-FEATURES-SPLIT-1 — `exit_features.rs` 1317 行拆為 4 檔目錄（2026-04-21）

**觸發**：上一 commit `e95c779`（TRACK-P-T4-WIRING-1）後 `rust/openclaw_engine/src/exit_features.rs` 長度 1317 行，超 §七「文件大小限制」1200 行硬上限。2026-04-21 報告 `.claude_reports/20260421_191842_track_p_t4_wiring.md` §4 治理對照已 flag。本 refactor 為跟進項，純檔案佈局重構，零語意改動。

**拆分結構**：

```text
rust/openclaw_engine/src/exit_features/
├── mod.rs        68 行   # 頂層 doctrine + pub use re-exports
├── core.rs      204 行   # ExitFeatures + PhysicalDecision（types + 7 core tests）
├── v2.rs        747 行   # ExitConfig + non_linear_giveback_fn
│                          # + physical_micro_profit_lock_v2（24 v2 tests）
└── builder.rs   368 行   # build_exit_features_for_tick（T4 wiring + 12 builder tests）
```

- **mod.rs**：Track P 文檔（§七 Phase 1b 段 + EXIT-FEATURES-SPLIT-1 佈局說明）+ 三個 `pub use` re-export 保向後相容：
  - `pub use crate::exit_features::core::{ExitFeatures, PhysicalDecision};`
  - `pub use crate::exit_features::v2::{physical_micro_profit_lock_v2, ExitConfig};`
  - `pub use crate::exit_features::builder::build_exit_features_for_tick;`
  - `non_linear_giveback_fn` 刻意保持 `pub(crate)` 不 re-export（只 v2 tests 內部呼叫，避免 crate-private 介面外洩）。
- **core.rs**：純 types；`ExitFeatures` 8 欄位 + `PhysicalDecision::{Hold, Lock(String)}` + serde 測試（ctor round-trip / None-field ctor / variant equality / est_net_bps=None 序列化 / atr_pct=0.0 邊界 / time_since_peak_ms 60k 邊界 / PhysicalDecision::Hold 往返）。
- **v2.rs**：`ExitConfig` 7 欄位 + `Default` + `validate()` + `non_linear_giveback_fn` + `physical_micro_profit_lock_v2` 4-Gate pure fn；模組頂部頁更新 Gate 1 v2 對齊 doctrine（GATE1-REVERSAL-1 hotfix A `d0f0c21` 後 v1 + v2 共享 Gate 1 Hold 語意，v2 額外保留非線性 giveback 閾值）；24 測試覆蓋 Gate 1-4 + 非線性 fn 單調性 + ExitConfig 驗證 + Option=None 保守路徑 + end-to-end Gate 1→Gate 4a Lock。
- **builder.rs**：`build_exit_features_for_tick` pure fn（7 維衍生鏡像 close-time `tick_pipeline::build_exit_feature_row`）；12 測試含 happy path / short-side / fresh-high 夾 0 / None ATR / 非正 ATR / legacy peak ts / same-tick peak / clock skew / entry 0∞ / end-to-end feed v2 Gate 4a Lock / missing edge Hold；tests 模組 `use super::super::v2::{physical_micro_profit_lock_v2, ExitConfig}` 跨模組 import 做 end-to-end 驗證（Rust module tree 標準做法）。

**外部呼叫零改動**：4 個 crate-local caller（`risk_checks.rs` L21 `use crate::exit_features::{ExitFeatures, PhysicalDecision}` / `tick_pipeline/on_tick.rs` × 3 個 `crate::exit_features::…` 呼叫 / `position_risk_evaluator.rs` L21 同 / `combine_layer.rs` L34 `use crate::exit_features::PhysicalDecision`）全部維持原 path，由 `mod.rs` 的 `pub use` re-export 解析。

**Tests**：engine lib **1839 passed / 0 failed**（與 split 前一致；43 exit_features 測試分佈到 core 7 / v2 24 / builder 12，0 regression）。

**檔案變更**（2 changed — `git rm` 1 + create 4 = net +4，total +1,391/-1,317）：
- `rust/openclaw_engine/src/exit_features.rs`（刪除，1317 行）
- `rust/openclaw_engine/src/exit_features/mod.rs`（新增，68 行）
- `rust/openclaw_engine/src/exit_features/core.rs`（新增，204 行）
- `rust/openclaw_engine/src/exit_features/v2.rs`（新增，747 行）
- `rust/openclaw_engine/src/exit_features/builder.rs`（新增，368 行）

**治理對照**：§七「文件大小限制」四檔全部 ≤ 800 行警告線（mod 68 / core 204 / v2 747 / builder 368），最大 v2.rs 747 < 800，無需再拆。`on_tick.rs` 2079 行仍超硬上限 — 屬另案 legacy bloat，不在本 ticket scope。

**Workflow**：operator 明確指示「先做 EXIT-FEATURES-SPLIT-1」；Mac 本地 `cargo check --lib` + `cargo test --lib exit_features::` + 全 engine lib 1839 → 1839 無 regression → commit + push → Linux release 驗證（本 commit 同鏈接 ssh）。未派 sub-agent（refactor scope 小且機械性，主 session 直接處理更快）。

---

### TRACK-P-T4-WIRING-1 — Priority 6 PHYS-LOCK runtime 接線（2026-04-21 · commit `e95c779`）

**觸發**：2026-04-21 晚 2 Linux audit 揭露 `tick_pipeline/on_tick.rs:1677` 硬編碼 `|_| None`，Priority 6 `physical_micro_profit_lock` 在生產從未 fire（`trading.fills` `risk_close:phys_lock_*` 0 筆 / 24h engine log `phys_lock` 0 matches）。Track P 全體（MICRO-PROFIT-FIX-1 2026-04-17 + Phase 1b v2 `aee96b9` + GATE1-REVERSAL-1 hotfix A `d0f0c21`）代碼對齊設計但 runtime 影響 = 0。設計文件 §七 Phase 1 軌道 1 L271-276 漏列「T4 builder 實作」為獨立交付項。

**修復**：
- 新 pure fn `exit_features::build_exit_features_for_tick(&PositionExitSnapshot, current_price, atr_pct, price_roc_short, est_net_bps, ts_ms) -> ExitFeatures`，鏡像 close-time `tick_pipeline::build_exit_feature_row` 的 7 維衍生規則（peak_pnl_pct / current_pnl_pct / giveback_atr_norm / time_since_peak_ms / entry_age_secs），可脫離 TickPipeline 單測。
- `tick_pipeline/on_tick.rs:1677` 舊 `|_| None` 替換為實際 closure：逐 PositionRow 查 `paper_state.position_exit_snapshot(&symbol)` + `price_tracker.compute_roc(&symbol, 300)` + `intent_processor.edge_estimates().get_cell(snap.owner_strategy, symbol).shrunk_bps` → 餵 builder → 產 `Some(ExitFeatures)`。
- Closure 僅捕獲 self 的 immutable sub-borrow（`paper_state` / `price_tracker` / `edge_estimates`），與既有 `&risk_config` 共存；借用於 `evaluate_positions` 返回後結束，不妨礙後續 `risk_closed_symbols` dispatch 的 `&mut self`。
- Fail-soft：任一 Option::None → 4-Gate 保守 Hold（pre-T3 語意，零 regression 風險；最壞情況 builder 全欄位 None = 等同舊 `|_| None`）。

**Runtime 效果**（待 Linux `restart_all.sh --rebuild` 部署）：
- Priority 6 4-Gate `physical_micro_profit_lock`（v1 linear `PhysLockConfig`）每 tick 評估活躍持倉。
- 合法 Lock 唯二 `phys_lock_gate4_giveback`（giveback ≥ 線性閾值）/ `phys_lock_gate4_stale_roc_neg`（peak 陳舊 + 短窗 ROC < 0）。
- Gate 1 (edge floor) 在 `edge_estimates` 冷啟動（`is_populated()=false`）時全 Hold — 預期 fail-safe，不是 bug；Phase 5 edge 收斂後自然解鎖實際 Lock。
- v2 非線性 giveback + `ExitConfig` swap 留待後續 TODO `TRACK-P-V2-SWAP-1` (P2，~1d)。

**Tests** (+12，全在 `exit_features::tests`)：
- `test_build_for_tick_long_profit_happy`：happy path，8 欄位完整填值，arithmetic 對齊手算
- `test_build_for_tick_short_profit_side_sign`：空倉側符號對稱
- `test_build_for_tick_giveback_clamped_to_zero_when_fresh_high`：current > peak 時 giveback 夾回 0
- `test_build_for_tick_atr_none_giveback_none` / `test_build_for_tick_atr_nonpositive_giveback_none`：ATR None / 0 / 負 / NaN → giveback None
- `test_build_for_tick_legacy_peak_ts_none`：legacy snapshot (peak_reached_ts_ms=0) → time_since_peak_ms None
- `test_build_for_tick_peak_same_tick_zero`：ts_ms == peak_reached_ts_ms → Some(0)
- `test_build_for_tick_clock_skew_entry_age_none`：ts_ms < entry_ts_ms → entry_age_secs None
- `test_build_for_tick_entry_price_zero_defensive` / `test_build_for_tick_entry_price_nonfinite_defensive`：entry 0 或 ∞ → current_pnl_pct=0.0
- `test_build_for_tick_feeds_v2_gate4_lock`：builder → v2 Gate 4a Lock 端對端
- `test_build_for_tick_none_edge_feeds_v2_hold`：missing edge → v2 Gate 1 保守 Hold

**測試**：engine lib 1827 → **1839 passed / 0 failed**（Mac debug + Linux release 均驗）。

**檔案**（2 changed, +410/-8）：
- `rust/openclaw_engine/src/exit_features.rs`（+355：builder + tests；962 → 1317 行，超 §七 1200 硬上限 ⚠️ 後續獨立 ticket `EXIT-FEATURES-SPLIT-1` 拆分）
- `rust/openclaw_engine/src/tick_pipeline/on_tick.rs`（+55/-8：T4 接線點；2024 → 2079 行，既有 legacy bloat 另案）

**Workflow**：主 session 直接寫（scope 小 ~50 LOC code + tests），未派 sub-agent。Mac `cargo check --lib` + `cargo test --lib exit_features::` + 全 engine lib 1839 綠 → commit + push → `ssh trade-core "git pull --ff-only && cargo test --release"` 1839 綠 → docs 二次 commit。

---

### EDGE-P2-3 Phase 2+ (b) bb_breakout + ma_crossover PostOnly entry wiring（2026-04-21 · merges `f5f4dc2` + `8280132`）

**觸發**：兩個 2026-04-20 分工平行 feature 分支（`ma_crossover_postonly` / `bb_breakout_postonly`）rebase 上 main 後依次 `--no-ff` merge 收尾；兩者鏡像 grid_trading Phase 1A 的 `default_use_maker_entry` / `default_maker_price_offset_bps` / `default_maker_limit_timeout_ms` + `grid_trading::clamp_maker_limit_timeout_ms` shared helpers，把 PostOnly Limit entry path 擴展到第二、三個策略。Close path 不動，維持 entry-only scope。

**Rebase 衝突處理**（CC 解）：`bb_breakout_postonly` 與 main 在 `bb_breakout.rs`（7 hunks：struct / Default / runtime / ctor / update_params / get_params / test module）+ `settings/strategy_params_{demo,live,paper}.toml` 衝突；HEAD 帶 EDGE-P2-2 Phase A OI confluence signal（`enable_oi_signal` / `oi_buffer_window_ms` / `oi_confluence_bonus` / `oi_min_delta_pct`），branch 帶 EDGE-P2-3 Phase 2+ (b) PostOnly entry（`use_maker_entry` / `maker_price_offset_bps` / `maker_limit_timeout_ms`）——兩組 feature 正交，全部保留並排放。Test module 特別處理：HEAD 647 行 OI tests + branch 133 行 PostOnly tests 之間補上缺失的 `}` 關閉 `fn test_oi_min_delta_pct_validation` 避免編譯斷裂。`ma_crossover_postonly` 自動 merge（branch 僅加新欄位，無衝突）。

**Operator 加碼**（merge 後）：三個 env TOML `[ma_crossover]` section 補上 `use_maker_entry` + `maker_price_offset_bps` + `maker_limit_timeout_ms`（demo/paper = true，live = false，與 bb_breakout 對齊）。

**改動**（2 feature commit + 2 merge commit）：

1. `9edc6a4` — bb_breakout：`BbBreakoutParams` 3 PostOnly 欄位 + Default + runtime + ctor + update_params + get_params + 4 新 unit tests；`mod.rs` `BbBreakoutParamsToml` 接線；三環境 TOML 加欄位（demo/paper true、live false）。
2. `b2d8ac5` — ma_crossover：`make_intent_with_qty` 依 `use_maker_entry` flag 解析 order shape（PostOnly Limit BUY below / SELL above last_price，否則 Market）；Close path 不變；+4 tests；三環境 TOML 加欄位。
3. `f5f4dc2` — `merge: EDGE-P2-3 Phase 2+ (b) ma_crossover PostOnly entry wiring`（`--no-ff`，fast-forward-safe rebase 後）。
4. `8280132` — `merge: EDGE-P2-3 Phase 2+ (b) bb_breakout PostOnly entry wiring`（`--no-ff`，CC 手動解 7 hunks + TOML 3 hunks 後）。

**驗證**：
- `cargo test -p openclaw_engine --lib` (debug)：**1827 passed / 0 failed / 0 ignored**（baseline 1819 + 4 bb PostOnly + 4 ma PostOnly）/ 0.52s。
- Fee routing 沿用既有 `intent_processor::fee_rate_for_intent`（strategy-agnostic，keys off `intent.time_in_force`），3 個 PostOnly 策略（grid / bb_breakout / ma_crossover）現走同一條 maker-fee path。
- Live 端三個 TOML 全部 `use_maker_entry = false`（root principle #6 保守；demo 驗證正 net edge 後再評估 flip）。

**Runtime 狀態**：engine binary 未重新部署（當前 PID 3813984 不含此兩 commit）；下次 `restart_all.sh --rebuild` 才進 runtime。部署前三個 PostOnly 策略 live TOML 均保留 `false`，風險為零。

**清理**：`bb_breakout_postonly` + `ma_crossover_postonly` 本地分支已 merged 進 main（可 `git branch -d` 安全刪除）；遠端 `origin/feature/p1-16-h0-gate-deterministic` tip `372432f` 已在 origin/main 上（可刪）。

### TODO 1+2 outcome_backfiller wiring fix（2026-04-21 · commit `5e2981d`）

**觸發**：前輪 session 發現 `trading.decision_outcomes` 兩個 P1 bug：
- **TODO 1 `DECISION-OUTCOMES-ENGINE-MODE-TAG-BUG-1`**：264,800 rows 100% `engine_mode='paper'`，但 `context_id` 前綴涵蓋 demo/live/live_demo。根因：`outcome_backfiller.rs` INSERT 省略 `engine_mode` 欄位 → `V015` 遷移的 `DEFAULT 'paper'::text` 兜底（migration L64-66 明確寫 "No writer exists yet"）。
- **TODO 2 `OUTCOME-BACKFILL-JOIN-NULL-1`**：264,800 rows 100% NULL outcome_* / MFE / MAE。根因：writer LATERAL subquery 用 Bybit API interval 字串（`'1'/'5'/'60'/'240'`），但 `market.klines.timeframe` 儲存格式是 `'1m'/'5m'/'1h'/'4h'`（ingest 時 normalize 過）→ 每個 LATERAL 回 NULL。

**改動**（2 檔 / Rust + 診斷 SQL）：

1. `rust/openclaw_engine/src/database/outcome_backfiller.rs`
   - Inline SQL 抽出成 `pub(crate) const BACKFILL_SQL: &str`（便於單測斷言字串形狀）。
   - 7 處 timeframe 字串替換：`'1'→'1m'`（price_1m + MFE `MAX(high)` + MAE `MIN(low)`）、`'5'→'5m'`、`'60'→'1h'`、`'240'→'4h'`（×2：price_4h + price_24h 都用 4h klines）。
   - 新增 `engine_mode` 傳遞鏈：pending CTE SELECT → outcomes CTE SELECT → INSERT column list → INSERT SELECT final column。
   - 新增 3 個 `#[cfg(test)]` 回歸測試：`sql_uses_klines_timeframe_storage_format`（4 正面 + 4 負面 assertion）、`sql_propagates_engine_mode_into_insert`、`sql_24h_window_uses_4h_timeframe`。

2. `helper_scripts/db/audit/2026-04-21--decision_outcomes_bugs_diagnostic.sql`（新增）
   - 可重跑的診斷腳本：SPLIT_PART 前綴 × engine_mode 交叉表、`market.klines.timeframe` distinct 值、fixed vs buggy LATERAL 並排、rows need re-backfill 規模。
   - 附 fix spec 注釋（L91-103）供未來 audit 對照。

**驗證**：
- `cargo test --release -p openclaw_engine --lib` → **1819 passed / 0 failed**（baseline 1816 + 3 new regression）。
- `bash helper_scripts/restart_all.sh --rebuild` 部署新 binary（`rust/target/release/openclaw-engine` stat = 16:01:37）。
- 歷史回填 TODO 1：`UPDATE trading.decision_outcomes SET engine_mode = ...` **267,400 rows**。
- 歷史回填 TODO 2：`/tmp/openclaw/backfill_outcomes_historical.sql` LATERAL UPDATE **267,776 rows**（post-commit 248,963 / 269,200 = 92.5% outcome_1m non-NULL；live 99.9% / demo 92.4% / live_demo 77.9%；剩餘 NULL 由 `market.klines` 資料缺口造成，屬 LEARNING-PIPELINE-DORMANT-1 範疇）。
- engine_mode 分佈對齊：`demo|demo|133944`、`live|live|89734`、`live_demo|live_demo|45522`（無 mismatch）。

**Mac-end 關聯**：TODO 3 `GATE1-REVERSAL-OBSERVABILITY-1` 本輪不動，Mac 端已 doc-only 關閉（commit `663f670`）；`TRACK-P-T4-WIRING-1`（production caller `tick_pipeline/on_tick.rs:1677` 的 `|_| None` 真實接線）留待後續 sprint 獨立處理。

### Linux trade-core 部署 + startup noise 清零 + P0-2 解耦 + GATE1-REVERSAL-OBS-1（2026-04-21 · commit `6b1b10d`）

**觸發**：Mac 端 `d0f0c21`（GATE1-REVERSAL-1 hotfix A）pull 至 Linux trade-core 後完整部署；同時 operator 要求把歷來兩個 pre-existing startup warning 一併修掉（不是本次引入，但累積多 commit 未處理，`restart_all` 日誌被噪音稀釋）。

**改動**（5 檔 / 純 Python + 文檔）：

1. `program_code/.../app/strategy_wiring.py` L407 — `from program_code.local_model_tools.cognitive_modulator import CognitiveModulator` → `from local_model_tools.cognitive_modulator import ...`
   - 根因：同檔 L65 已 `from . import _path_setup` 把 `program_code/` 加 `sys.path`，但 L407 用長形式 `from program_code....` 要求 `srv/`（program_code 的 parent）在 sys.path，該路徑從未被加。與同檔 L67-70 短形式不一致。
   - 效果：`restart_all.sh` log 上 `Could not inject CognitiveModulator: No module named 'program_code'` 從 4×/ restart 歸零；`STRATEGIST_AGENT.set_cognitive_modulator` 真實執行（此前 try/except 吞錯下，L0 決策門檻調制一直沒綁上）。

2. `program_code/.../app/ai_service.py` — 加 `import errno` + `import socket as _socket_stdlib`；`AIServiceListener.start()` 前加 multi-worker guard；新增 `_probe_unix_listener_alive(path, timeout=0.1)` module helper。
   - 根因：uvicorn `--workers 4` 下 4 workers 並行 `os.unlink + asyncio.start_unix_server`，unlink-war 導致 ≥2 個 LISTEN 指向同 path、殘 FD 不確定，`ss -xl` 實測兩 inode 並存。
   - 守衛邏輯：probe connect → peer listener 活 = 被動跳過；殘留窄 race 用 `EADDRINUSE` 軟吞降級。
   - 效果：`ss -xl | grep ai_service` 從 2 LISTEN → **1 LISTEN**；log 上 `AIServiceListener.start() failed: Address ... already in use` 從 2× → 0；`connect('/tmp/openclaw/ai_service.sock')` probe OK。Rust engine IPC 行為不變（仍一對一）。

3. `CLAUDE.md` §十 — P0-2 21d demo 時鐘錨定敘述更新：從「當前 PID 1364222 於 22:16 local 啟動，時鐘從此起算」改為「時鐘從 **2026-04-16 22:16 local**（P0-9 STABILITY-1 RCA 穩定點）起算；PID 已多次輪替，當前 engine PID `3813984` 於 2026-04-21 13:44 CEST rebuild restart 起，計劃性 rebuild/deploy 不重置時鐘，僅 crash/hang 才重置」。
   - 修正 PID 指針 stale 4 天（1364222 實際 2026-04-17 20:55 已被 MICRO-PROFIT-FIX-1 取代為 1771173，後續多次輪替未更新）。
   - 明確 PID 與 21d 時鐘解耦原則，避免未來每次 deploy 都混淆。

4. `TODO.md` — 新增 `P1-18 · GATE1-REVERSAL-OBS-1` 條目。
   - 基準線時間戳：`2026-04-21 13:44:54 CEST (epoch 1776771894)` / engine PID `3813984`。
   - 4 觀察指標（`phys_lock_gate1_low_edge` 新 fills=0 / 持倉時長分佈 / close 盈利右尾 / edge_estimates shrunk_bps）。
   - Gate：≥2-3d 未惡化 → 解鎖下一波 Priority 6 全替換（DUAL-TRACK-EXIT-1 Phase 2/3 Track P）。

5. `docs/CLAUDE_CHANGELOG.md` — 本條目。

**部署執行**：
- `bash helper_scripts/restart_all.sh --rebuild`：release 增量 23.51s；engine PID `3813984`；`execution_authority` T0 Entry 剩 12.4h auto-restored。
- `cargo test -p openclaw_engine --lib --release`：**1816 passed / 0 failed / 0.51s**（與 Mac debug 對齊）。
- `bash helper_scripts/restart_all.sh --api-only`（pre-existing fix 部署，不動 engine，保留觀察基準線）：4 workers Application startup complete；0× CognitiveModulator warning；0× AIServiceListener warning；1 LISTEN；probe OK。
- targeted pytest（`-k "ai_service or listener or strategy_wiring or cognitive"`）：**15 passed / 1 skipped / 0 failed**。

**未動**：兩個 `WARNING: database "trading_ai" has no actual collation version` 屬 Postgres initdb locale 問題、與本系統無關，不處理。

**後續**：2-3d 觀察窗由 P1-18 接管；通過後進 Priority 6 全替換。



**目標**：上一 commit `aee96b9` DUAL-TRACK-EXIT-1 Phase 1b v2 交付後，主會話 QC 揭露 v1 `risk_checks::physical_micro_profit_lock` Priority 6 Gate 1 行為（`edge < floor → Lock`）違反 DUAL-TRACK-EXIT-1 設計意圖「防止剛有大於 fee 的微利就套離場」。Operator 選 (A) 獨立 hotfix commit 立即修 v1，不等下一波 Priority 6 整體替換。理由：v1 是 live 行為，continue 會在 demo 持續產出過早 close 紀錄，壓低 Phase 5 edge 觀察信號純度。

**改動**（2 檔 / ±18 LOC）：
- `rust/openclaw_engine/src/risk_checks.rs`：
  - L230-239 PHYS-LOCK 模組 comment：明確 active emits = `phys_lock_gate4_giveback` / `phys_lock_gate4_stale_roc_neg`；`phys_lock_gate1_low_edge` 標為 historical/backward-compat（v1 不再 emit，下游 `strip_phys_lock_prefix` + `parse_exit_tag` 保留解析）
  - L293-313 `physical_micro_profit_lock` doc：Gate 1 敘述改 `edge < floor → Hold (prevents micro-profit premature lock)`；整段「Lock is reached **only** via Gate 4 (trailing)」加粗
  - L316-326 Gate 1 分支：`PhysicalDecision::Lock("phys_lock_gate1_low_edge".to_string()) → PhysicalDecision::Hold`
  - L918-932 `test_phys_lock_gate1_low_edge_triggers_lock` → rename `_holds`，assert 改 `PhysicalDecision::Hold`
  - L1015-1044 `test_phys_lock_reason_string_format_stable`：刪 gate 1 段（7 行），保留 gate 4a/4b
  - L716-744 `test_tick_priority6_phys_lock_fires_with_features` → rename `_gate1_holds_with_low_edge`，assert 反轉為 `!ClosePosition`
- `rust/openclaw_engine/src/position_risk_evaluator.rs`：
  - L317-352 `test_evaluate_position_phys_lock_fires_with_features` → rename `_gate1_holds_with_low_edge` + doc 更新 + assert 反轉

**未動（刻意留下一波 Priority 6 替換時處理）**：
- Gate 1 `<` → `<=` 符號統一（與 v2 對齊）
- Gate 4b `>` → `>=` 符號統一
- `phys_lock_gate1_low_edge` 字串常量從 `on_tick.rs` t4_fix + `tick_pipeline/mod.rs` infer_source + Python `parse_exit_tag` 的清理（需所有含此 tag 的歷史 fills 歸檔或過期後）
- Priority 6 整體替換 v1 → v2 `physical_micro_profit_lock_v2` + `ExitConfig`
- ConfigStore ArcSwap 綁定 `ExitConfig`
- 非線性 giveback 3 參數校準（counterfactual replay 7d）

**驗證（Mac debug）**：
- `cargo test --lib risk_checks`：**35 passed / 0 failed**
- `cargo test --lib position_risk_evaluator`：**11 passed / 0 failed**
- `cargo test --lib`（全量）：**1816 passed / 0 failed**（不變 — rename 等價、刪除 1 個 assert 段 + Gate 1 Hold 邏輯路徑由整合測試覆蓋）

**設計一致性**：v1 和 v2 現已語意一致 — Gate 1 Hold / Lock 路徑唯一 = Gate 4 trailing。

**Linux 端部署步驟（→ operator）**：
1. `git pull origin main`
2. `bash helper_scripts/restart_all.sh --rebuild` 把行為推到 runtime
3. 記錄時間戳作為 demo 新行為基準線
4. 2-3d 觀察期：`phys_lock_gate1_low_edge` 新 fills 應歸 0；對比 demo 平均持倉時長 / 單筆 close 盈利分佈 / Phase 5 edge 指標
5. 若觀察期 edge 未惡化 → 進入下一波 Priority 6 替換

**TODO 狀態**：`GATE1-REVERSAL-1` 從 `[ ]` 改為 `[~]`（部分完成：hotfix A 已結，剩餘符號統一 + Priority 6 替換留下一波）。

---

### DUAL-TRACK-EXIT-1 Phase 1b Track P v2 非線性 giveback pure fn（2026-04-21 · commit `aee96b9`）

**目標**：推進 DUAL-TRACK-EXIT-1 主軸 Phase 1b 軌道 1 — 在既有 v1 `risk_checks::physical_micro_profit_lock` 線性閾值版（MICRO-PROFIT-FIX-1 / 2026-04-17 已上線）之外，新增 v2 **非線性 giveback** pure fn + 7 參數 `ExitConfig`，作為下一波 Priority 6 替換的基礎。設計意圖（operator QC）：「防止剛有大於 fee 的微利就套離場；保證 trailing stop；追求最高單筆 close 盈利」。

**改動**（1 檔 / +698 / -0 LOC）：
- `rust/openclaw_engine/src/exit_features.rs`（191 → 889 行）：
  - **`ExitConfig` struct** 7 欄位（`min_net_floor_bps=5.0` / `min_hold_secs=30` / `min_peak_atr_norm=0.5` / `stale_peak_ms=60_000` / `giveback_base=1.0` / `giveback_slope=0.15` / `giveback_floor=0.3`）+ `Default`/`validate()`/serde round-trip
  - **`non_linear_giveback_fn(peak_atr_norm, cfg) -> f64`**：linear decay + floor bound — `max(base − slope × norm, floor)`；NaN/Inf/負值夾回 0.0 → 回 base（total over all f64 inputs）
  - **`physical_micro_profit_lock_v2(&ExitFeatures, &ExitConfig) -> PhysicalDecision`** 4-Gate 非線性 pure fn：
    - Gate 1 `edge <= floor → Hold`（**設計意圖**：防止微利即套離場；QC 反轉 v1 Lock 語意）
    - Gate 2 `entry_age_secs < min_hold → Hold`
    - Gate 3 `peak_pnl_pct / atr_pct < min_peak_atr_norm → Hold`
    - Gate 4a `giveback_atr_norm >= non_linear_giveback_fn(peak_atr_norm) → Lock("phys_lock_gate4_giveback")`
    - Gate 4b `time_since_peak_ms >= stale_peak_ms AND price_roc_short < 0 → Lock("phys_lock_gate4_stale_roc_neg")`
    - 保守：任一所需 `Option::None` 回 Hold；Lock 唯一合法路徑 = Gate 4
  - **31 單測**：Gate 1-4 覆蓋 + 非線性 fn 單調性 / 高峰值 floor / 低峰值 base / NaN 保護 + ExitConfig validate 7 不變量 + serde round-trip + Gate 1 Hold 後 Gate 4 端到端觸發驗證

**QC 反轉過程**：
- E1 第一輪：無條件對齊 v1 `edge < floor → Lock`，doc comment 自我解釋「insufficient net edge is itself decisive signal」
- 主會話 QC：揭露此違反設計文檔 §三 L108-111 偽代碼（`<= → Hold`）+ operator 明確 DUAL-TRACK-EXIT-1 設計要求「防止剛有大於 fee 的微利就套離場 / 保證 trailing stop / 追求最高單筆 close 盈利」
- E1 回修：Gate 1 分支反轉 `Lock → Hold` / 刪除 `phys_lock_gate1_low_edge` reason 字串 / Test 1/2 rename `_locks → _holds` + assert 改 Hold / Test 22 assert 改 Hold / 新增 Test 25 端到端 Gate 1 Hold 後 Gate 4 trailing 觸發驗證

**v1 `risk_checks.rs:312-323` 仍為 Lock 語意**（本輪 operator 指示「不動 Priority 6」）→ 新 TODO `GATE1-REVERSAL-1`（P1）追蹤下一波替換時：(1) 修 v1 Gate 1 → Hold (2) 統一符號 Gate 1 `<` → `<=` / Gate 4b `>` → `>=` 對齊設計文檔 (3) 接 ConfigStore ArcSwap hot-reload (4) Combine Layer 骨架。

**驗證（Mac debug）**：
- `cargo check --lib`：綠（6 預存 warnings）
- `cargo test --lib exit_features`：**31 passed / 0 failed**（24 E1 第一輪 + 3 QC rename + 4 增補：Gate 1→4 端到端 + non_linear 單調 + validate 邊界 + serde round-trip）
- `cargo test --lib`（全量）：**1816 passed / 0 failed**（1791 基準 + 25 新測）
- `grep -cE '(/home/ncyu|/Users/[^/]+)' exit_features.rs` → 0 跨平台違規
- `grep 'phys_lock_gate1_low_edge' exit_features.rs` → 0（QC 後全清）

**工作流**：PM+FA（主會話 QC 對齊設計文檔 360 行）→ E1（general-purpose sub-agent 寫碼）→ E2（主會話 QC 揭露 Gate 1 反轉）→ E1 回修 → E4（cargo test 1816/0）→ PM（本 CHANGELOG + CLAUDE.md §三/§十一 + TODO.md + `.claude_reports/20260421_132015_dual_track_exit_phase1b_v2.md` + commit + push）。Mac dev-only，1 E1 sub-agent 無 refuse。

**不確定之處**（→ operator 下次 Linux session 處置）：
- v1 Priority 6 本週是否 hotfix（獨立 commit）還是等下一波替換 — 目前 v1 行為「edge < 5 bps 立即 Lock」= greedy 微利鎖，違反設計意圖，demo 可能正在累積「不該有的 close 紀錄」
- ExitConfig 7 閾值 default 未經 demo 資料校準（Mac 做不了 counterfactual replay 7d tick-level audit）
- 檔案大小 889 行已過 800 警告線，下一波 Priority 6 替換前建議 split

**commit 歷程**（本次同 commit 一次交付）：
- `rust/openclaw_engine/src/exit_features.rs`（+698）
- `TODO.md`（Phase 1b 進度更新 + `GATE1-REVERSAL-1` 新條目 + 基準線 1816）
- `CLAUDE.md`（§三 2026-04-21 里程碑行 + §十一 一句話狀態）
- `docs/CLAUDE_CHANGELOG.md`（本條目）
- `memory/MEMORY.md` + `memory/project_dev_runtime_split.md`（Mac dev-only runtime split 記憶）

---

### PYO3-ELIMINATE-1 Phase 3：drop openclaw_pyo3 crate + build pipeline（2026-04-20 · commit `9b691a0`）

**目標**：消除 PyO3 cdylib 跨平台耦合最後一塊 — 在 Phase 1（刪 ContextDistiller/HedgingEngine 513 LOC）+ Phase 2（`BybitClient` 3 call sites 遷 httpx）後，拆 crate + 清工具鏈讓 `rg '#\[pyclass\]|from openclaw_core'` 歸零、Mac `cargo build` 只產 binary 無 .so/.dylib。

**改動**（18 檔 / +40 / -1420 LOC 淨 -1380）：
- `git rm -rf rust/openclaw_pyo3/`（Cargo.toml + pyproject.toml + src/bybit_bridge/\*.rs + lib.rs；8 檔 ~918 LOC）
- `rust/Cargo.toml`：workspace members 4→3（移除 `openclaw_pyo3`）+ 移除 `pyo3 = { version = "0.24" }` workspace dep
- `git rm helper_scripts/build_pyo3.sh`（285 LOC maturin build + dual-venv pip install）
- `helper_scripts/restart_all.sh`：移除 `rebuild_pyo3()` function + 呼叫；MODULE_NOTE 更新（`--rebuild` 只剩 engine binary）；pre-flight 注釋反映新單一建構產物語意
- `helper_scripts/clean_restart.sh` + `helper_scripts/fresh_start.sh`：`SRC_DIRS` 移除 `rust/openclaw_pyo3/src`（binary freshness 掃描）
- `helper_scripts/SCRIPT_INDEX.md`：移除 `build_pyo3.sh` 列 + 更新 `restart_all.sh` 說明
- `README.md`：架構圖 4→3 crates + 亮点「PyO3 39 方法」→「PYO3-ELIMINATE-1 完成（純 Python httpx）」+ 建構章節移除（pure Python API 無 build step）+ `restart_all` 旗標說明更新
- `CLAUDE.md §九 singleton 表`：`_RUST_BYBIT_CLIENT` → `_BYBIT_CLIENT` / `_BYBIT_CLIENT_AVAILABLE`（函數名 `_get_rust_client()` 為 grep-stability 保留）
- `TODO.md §PYO3-ELIMINATE-1`：Phase 1 `[x]` commit `a84ecdb` + Phase 2 `[x]` commit `0f8220b` + Phase 3 全 `[x]`（commit 待填）

**驗證**：
- `cargo build --release -p openclaw_engine`（在 `rust/` workspace）：11.14s 綠，warnings 為預存 `openclaw_engine` dead_code（非 Phase 3 引入）
- `cargo test --release -p openclaw_engine --lib`：**1791 passed / 0 failed**（0.52s）
- pytest `test_bybit_rest_client.py` + `test_bybit_rest_client_parity.py`：58 passed / 5 skipped（0.76s）
- `bash -n` syntax-check 三 restart 腳本：OK
- `git grep 'openclaw_pyo3\|build_pyo3\|rebuild_pyo3'` 活躍代碼/腳本 0 match（剩 TODO/worklog/audit/archive 歷史文件 — 預期）

**遷移量化（三 phase 總計）**：
- 刪除 LOC：Phase 1 513 + Phase 2 +914 code / -0（純新增 httpx client）+ Phase 3 -1420 = PyO3 surface 歸零
- 移除 `maturin` / `cibuildwheel` 跨平台 wheel 管道需求
- Rust workspace 4 crates → 3 crates；`pyo3 = "0.24"` workspace dep 消失
- Mac M5 (aarch64-apple-darwin) 部署阻力：PyO3 wheel cross-compile（唯一硬骨頭）→ **消失**
- `restart_all.sh --rebuild` 從「engine binary + PyO3 wheel dual-build」簡化為單一 `cargo build --release -p openclaw_engine`

**下一步**：
- 部署：直接 `bash helper_scripts/restart_all.sh --rebuild` — API 不需 build（純 Python），engine binary 從 rebuild 路徑下 11s 編好
- Mac 準備度：workspace 現在在 Linux + macOS 均可 `cargo build --release` 產 binary；Python `.venv` 跨平台安裝即可（移除了唯一的 ABI 耦合點）
- 回歸監控：FD leak（E2 F2.1）/ BybitError 例外類型（E2 F2.2）— 見 `docs/audits/2026-04-20--pyo3_eliminate_phase2_e2_review.md`

---

### EDGE-P2-2 Phase A: OI Confluence Signal + E2 FUP #1-#7（2026-04-20）

**目標**：為 `bb_breakout` 加 Bybit WS `tickers.openInterest` 領先信號 → `oi_delta_pct` 調製 `confluence_score` ±bonus。旗標 `enable_oi_signal` 預設 `false`，保證與 pre-EDGE-P2-2 baseline bit-identical。

**Session 2 前半（11:26–11:37 已寫碼）**：
- `openclaw_types::PriceEvent` +`open_interest: Option<f64>`（+10 行）
- `ws_client.rs` ticker 解析新增 OI 欄位（snapshot/delta 合併語義 + NaN/Inf 拒絕，+109 行）
- `tick_pipeline/mod.rs` + `on_tick.rs` 傳遞 OI 到 `TickContext`（+13/+8 行）
- `strategies/mod.rs` `TickContext` / `Strategy` trait contract 更新 + 4 非 bb_breakout 策略 `open_interest: None` 補丁
- `strategies/bb_breakout.rs` OI 邏輯 +620 行（`oi_buffer: VecDeque<(u64, f64)>` per-symbol + `compute_oi_delta_pct` + `apply_oi_confluence_modifier` + `BbBreakoutParams` 三新欄位 `enable_oi_signal`/`oi_buffer_window_ms`/`oi_confluence_bonus` + `ParamRange` 3 新條目 + `validate()` 新規則 + `update_params`/`get_params` 熱重載 + `prev_state` snapshot rollback + 8 新測試）
- TOML 三環境新欄位 `enable_oi_signal=false` + `oi_buffer_window_ms=60000` + `oi_confluence_bonus=0.10`

**E2 對抗性審查（Session 2 後半）**：派發對抗性審查找到 3 critical + 4 suggestion (#1–#7)。operator 命令「1-7 全部修掉再 commit」。

**FUP #1 — `oi_buffer` 被 trade/orderbook tick 稀釋**：
- **風險**：`ctx.open_interest=Some(oi)` 在非 ticker stream 上（同一 ticker snapshot 回寫）會重複入隊，縮短滾動窗口的真實時間覆蓋。
- **修復** `bb_breakout.rs::on_tick` OI push 區塊：改為 change-of-state 推入 — 只在 `ctx.timestamp_ms > back_ts && |oi - back_oi| > EPSILON` 時 `push_back`；否則丟棄。
- **測試**：`test_oi_buffer_deduplicates_same_value`（3 同值 + 1 變動 → len == 2）。

**FUP #2 — `on_rejection` 回滾錯誤丟棄 `oi_buffer`**：
- **風險**：`oi_buffer` 是**市場觀察**非**策略決策狀態**。rollback 把它跟著 prev_state 快照一起倒回去 → 下次估計用舊/空 buffer → 誤信 OI 估計。
- **修復** `on_rejection`：保留 `live_oi_buffer = self.symbols.get(sym).map(|s| s.oi_buffer.clone())`，在還原 prev_state 後覆寫回去；若 prev=None 但有新樣本 → 創建只含 oi_buffer 的 Default state（trading state 保持 unseen）。
- **測試**：`test_on_rejection_preserves_oi_buffer`（breakout Open → `on_rejection` → buffer len 不變 + back tuple byte-identical）。

**FUP #3 — `d != 0.0` 允許 WS 量化噪音觸發 bonus**：
- **風險**：Bybit WS `openInterest` 以合約張為單位，±1 張合約 quantisation → `oi_delta_pct ≈ 1e-8` 仍觸發 bonus。
- **修復**：新參數 `oi_min_delta_pct: f64`（noise floor，預設 0.0 維持 pre-FUP 語義），在 modifier 內 `if d.abs() > self.oi_min_delta_pct`；`validate()` 強制 `[0.0, 0.5] finite`；`ParamRange` 新條目 agent-adjustable。
- **測試**：`test_oi_min_delta_pct_below_threshold_no_effect`（floor=0.05, delta=2% → f32 bit-identical 於 flat 對照）+ `test_oi_min_delta_pct_validation`（NaN/負/>0.5 拒絕，0.0/0.5 邊界通過）。

**FUP #4 — TOML 啟動路徑 bypass runtime `validate()`**：
- **風險**：`StrategyFactory::create_with_params` 從 TOML 直寫 runtime，若 TOML 含惡意值（e.g. `oi_buffer_window_ms = 10_000_000`）會靜默注入壞參數。
- **修復**：`strategies/mod.rs::BbBreakoutParams` 新 `validate_oi()` helper 鏡射 runtime 規則，在 factory 呼叫：`Err(_)` → 記 `warn!` + 回退到 `default_bbb_oi_buffer_window_ms()` / `default_bbb_oi_confluence_bonus()` / `0.0`。
- **測試**：`test_edge_p2_2_fup4_factory_falls_back_on_invalid_oi`（壞值 → runtime JSON 回預設）+ `test_edge_p2_2_fup4_factory_passes_valid_oi`（合法值直通）。

**FUP #5 — `oi_buffer_window_ms` 缺上限校驗**：
- **風險**：hostile IPC 寫入 `u64::MAX` + 高頻 ticker → `VecDeque` 無元素上限 → 記憶體無界成長。
- **修復** `validate()` 新增 `> 600_000` 拒絕；`ParamRange.max = 600_000.0` 對齊（runtime 實際最大 10 min 窗口已覆蓋所有合理 use-case）。
- **測試**：`test_oi_window_upper_bound_validation`（600_001 失敗 / 600_000 通過）。

**FUP #6 — 跨 stream 交錯導致 ts 回溯**：
- **風險**：WS 多 topic 合流時可能出現 `ctx.timestamp_ms` 比 `back_ts` 小（stream 到達順序與交易所時戳順序不一致）。
- **修復**：FUP #1 的 `should_push` guard 已包含 `ctx.timestamp_ms > back_ts`（嚴格 >）；相同 ts 或回溯 ts 均丟棄。
- **測試**：`test_oi_buffer_skips_ts_regression`（ts=10000 入 → ts=5000 丟 → ts=10000 相同丟，len==1）。

**FUP #7 — bonus magnitude docstring 缺 operator 指引**：
- **修復**：`oi_confluence_bonus` docstring 加「Score bands no_trade(~30)→light(~40)→full(~45)，typical effective range 0.3-0.5 to move qty_pct by ≥5 pp；default 0.10 偏保守，適合首次 A/B」。

**TOML 三環境同步**：`strategy_params_{demo,paper,live}.toml` `[bb_breakout]` 新增 `oi_min_delta_pct = 0.0` + 更新註釋說明 validate 範圍。

**測試基準**：engine lib **1791 passed**（pre-EDGE-P2-2 baseline 1770 + 13 EDGE-P2-2 + 8 FUP = 1791；0 failed）。`test_bbb_param_ranges_count` 由 19 → 20 反映新增 `oi_min_delta_pct` ParamRange。

**部署準則**：預設旗標 `enable_oi_signal=false`，部署即生效但零行為變更；operator 啟動前需在 `strategy_params_demo.toml` 設 `enable_oi_signal = true`（先 demo 驗證 ≥7d edge 再評估 live）。

### DUAL-TRACK-EXIT-1 Phase 1a Track P E2+E4 驗收（2026-04-19 · worklog `2026-04-19-2--track_p_counterfactual_audit.md`）

**目標**：盤點 Track P T1-T5 單測總數（≥18 要求）+ 跑 T5 counterfactual audit CLI 事後歸因 Phase 1a 骨架閾值表現。

**單測盤點（≥47，遠超 ≥18 要求）**：
- T1 `exit_features.rs` 6 + `database/exit_feature_schema.rs` 3
- T2 `compute_roc` 專項 12（`price_tracker.rs` 總 30）
- T3 `physical_micro_profit_lock` 9（`risk_checks.rs` 總 35）+ evaluator wrapper 1
- T4 `combine_layer.rs` 9
- `tick_pipeline/tests.rs` `exit_feature_row` 7（5 pre-existing WIP + 2 GAP-1 regression）

**Counterfactual audit**（`program_code/audit/counterfactual_exit_audit.py` commit `4feb17a`，MARKET-KLINES-STALE-1 修復後 market.klines 持續寫入 `kline_fresh=true`）：
- **grid_trading demo 7d**（`/tmp/cf_audit_grid_demo.json`）：141 positions / 4 hits / delta_bps mean=−39.44 / p50=0 / p75=0；n_phys_better=1 vs n_phys_worse=2
- **ma_crossover demo 7d**（`/tmp/cf_audit_ma_demo.json`）：52 positions / 10 hits / delta_bps mean=−95.20 / p25=−62.49 / p75=+54.72；n_phys_better=5 vs n_phys_worse=5

**關鍵發現**：
1. 命中率低但方向分歧（grid 2.8% vs ma 19.2%）——骨架閾值對 grid 極度保守
2. **ENJUSDT 案例（grid）**：real +2.76% vs cf +0.78% = **−198 bps**。Track P `giveback_atr_threshold=0.6` + `min_peak_atr_norm=0.5` 的骨架預設會砍掉趨勢性大 winner
3. **BLURUSDT #2 案例（grid）**：real −0.01% vs cf +0.55% = **+55.7 bps**，Track P 成功救回 loser；但正面案例僅 1/4
4. ma_crossover p75=+54.7 bps 顯示「少數贏家 + 多數被提早砍」分佈，與 P1-10 STRATEGY-ASYMMETRY-1（ma R:R 2.54×）一致

**結論**：E2+E4 驗收通過；Phase 1a 骨架閾值對真實 demo 數據過於保守（與設計預期一致，詳 `docs/worklogs/2026-04-18--dual_track_exit_design.md` §Phase 1b 完成標準）；校準工作正確排入 Phase 1b（累積 ≥1 週 exit_features 後資料驅動 bind）。

**下一步**：等 Phase 1b exit_features 累積 ≥1000 rows 後重跑此 audit 驗證收斂；校準方向由資料決定，初步假設為提高 `min_peak_atr_norm` + `giveback_atr_threshold` + `min_net_floor_bps`。

### E5-FN-2 Plan N — ai_budget request_id dedup via existing hypertable PK（2026-04-19 · revert `87b7653` + commit `f0f11c0`）

**觸發**：原 `fd480ba`（FN-2 三段式修復）依賴 `V018__ai_usage_log_request_id_unique.sql` partial UNIQUE `WHERE request_id <> ''`。部署時 empirical 失敗：
```
ERROR: cannot create a unique index without the column "time" (used in partitioning)
```
TimescaleDB 2.26.1 hypertable 強制 UNIQUE index 必須含 partitioning column — V018 設計根本上無法 apply。

**RCA key insight**：`learning.ai_usage_log` 既有 PK `(time, scope, request_id)` 就是一個滿足 hypertable 約束的 UNIQUE constraint。只要 caller 傳入**確定性**的 `(time, request_id)` tuple（而非 `NOW()` 每次新值），既有 PK 直接做 `ON CONFLICT` dedup — 零新 schema、零 migration、零新 index。

**實施 Plan N**：
1. **Revert `fd480ba`** → `87b7653`（5 files, -386 insertions；V018 SQL 刪除）
2. **`ai_budget::make_request_id(scope: &str) -> (String, i64)`**：回 `(id, ts_ms)` tuple（格式 `{scope}-{ts_ms}-{hex8}`）— caller 重試必須傳同 tuple
3. **`usage_io::insert_usage`**：新 `event_time_ms: i64` 參數 → bind `$1::timestamptz`；SQL `INSERT ... ON CONFLICT (time, scope, request_id) DO NOTHING RETURNING 1`；回 `Result<bool, String>`（`false`=dedup）
4. **`tracker::record_usage`**：新 `event_time_ms: i64` 參數；`if inserted` 才累進 MTD cache，dedup 不雙重計費
5. **`claude_teacher/mod.rs:152`**：改用 `crate::ai_budget::make_request_id("teacher")` tuple 一次鑄造後傳回 record_usage
6. **IPC `handle_record_ai_usage`**：收 Python params 傳入 `(request_id, event_time_ms)` 或任一缺失時本地 `make_request_id(scope)` 鑄造；response 回 echo `request_id`/`event_time_ms` 方便 Python 持久化做未來重試。封閉 `fd480ba` 原本會引入的 `"py-sync"` literal PK 碰撞（V018 下所有 Python caller 共用同 id → 月初後每條被 dedup 掉）

**對比 fd480ba**：
- fd480ba: partial UNIQUE `WHERE request_id <> ''`（保留 V010 legacy `DEFAULT ''` rows）+ `ON CONFLICT (request_id) WHERE ... DO NOTHING` → 部署阻斷（hypertable 約束）
- Plan N: 既有 PK `(time, scope, request_id)` + 確定性 `event_time_ms` tuple → 部署無阻

**測試**（+4 in `ai_budget::tracker::tests`）：
- `test_make_request_id_format` — 三段 hyphen 結構 + 8 hex 後綴
- `test_make_request_id_unique_within_same_ms` — 隨機 hex 碰撞機率 ~1/2^32
- `test_record_usage_cold_start_still_increments_cache` — 無 DB 路徑視為新插入，cache 照常累進
- `test_record_usage_distinct_tuples_accumulate` — 3 次 distinct tuple 全部計入

**回歸**：engine lib 1567 → **1571 passed / 0 failed**（+4 Plan N）。
Python 端未變（IPC 參數為 optional，無 param 缺失時仍能本地鑄造）。

**部署硬約束**：~~V018 migration~~ 取消。直接 `bash helper_scripts/restart_all.sh --rebuild`。

**E2 self-review**：
- LiveDemo 不降級 — live-level 門控不受影響（FN-2 只觸及 learning schema，不涉及 authorization/risk/exec path）
- fail-closed 合約保留：DB write error 仍上拋 caller，caller 必須拒 LLM 調用
- Root Principle #13「AI cost 感知」守護：dedup 不雙重扣費 → cost_edge_ratio 不被 retry 噪音污染

---

### E5-FN-3 — `agent_audit_bridge.py` + AnalystAgent pilot wiring（2026-04-19 · commit 19f3d85）

Audit `docs/audits/2026-04-18--e5_full_codebase_audit.md` §七.7.3 聲稱 5-Agent 系統（Scout/Strategist/Guardian/Analyst/Executor）**無一寫入 `change_audit_log`** — 違反 Root Principle #8「交易可解釋」。RCA 驗證：

- Scout 類 ctor 硬編碼 `audit_callback=None`（`multi_agent_framework.py:410`）→ 0 `_audit()` calls
- Strategist 有 7 `_audit()` call-sites，Guardian 4，Analyst 6，Executor 2 → 共 **19** 個 call-sites
- `strategy_wiring.py` 4 agent 建構時**均未傳 `audit_callback=...`** → `BaseAgent._audit_callback=None` → 19 calls 全部 silently no-op
- 治理層 `governance_hub` 寫入 `change_audit_log` 覆蓋的是 state machines（authorization / risk_governor / decision_lease / reconciliation），**不覆蓋 agent 決策點**

**實施**：
- 新 `agent_audit_bridge.py`（+280 行，stateless 工廠）：
  - `make_agent_audit_callback(gov_hub, role_name) -> Callable[[str, Any], None]`
  - 分類策略：`*_received` → `STATE_CHANGE`，其他 decision-ish → `PARAMETER_CHANGE`（未知 event_type 落 `PARAMETER_CHANGE` 保守默認）
  - Fail-open 3 層守護（gov_hub=None → debug / `_change_audit_log` 缺席 → debug / `record_change` 拋異常 → warning）
  - `_change_audit_log` 每次 call lazy-read → 支援 late binding（test 覆蓋）
- **AnalystAgent pilot** on `strategy_wiring.py` Batch 9 (`:268`) + Batch 10 (`:342`)：
  - 模組級 `_GOV_HUB_FOR_ANALYST` + `_ANALYST_AUDIT_CB = make_agent_audit_callback(_GOV_HUB_FOR_ANALYST, "AnalystAgent")`
  - 兩 call site 均傳 `audit_callback=_ANALYST_AUDIT_CB`
  - Scout 維持 `audit_callback=None` 硬編碼（需 code change，屬 follow-up）
- CLAUDE.md §九 登記 `_ANALYST_AUDIT_CB` + `_GOV_HUB_FOR_ANALYST` + 註記 `agent_audit_bridge` 為無狀態工廠

**APPROVE_PARTIAL 延後（TODO §E5-FN-3-FUP）**：
- Strategist wire at `strategy_wiring.py:172`（7 calls exist）
- Guardian wire at `:215`（4 calls exist）
- Executor wire at `:345`（2 calls exist）
- Scout 需 code change：`multi_agent_framework.py:400` ctor 接受 `audit_callback=` kwarg + 新增 `_audit()` calls at `produce_intel()` / `produce_event_alert()` + wire at `:114`

**測試（+12 in `tests/test_agent_audit_bridge.py`）**：分類（兩桶）· 多事件持久化 · fail-open（gov_hub=None / audit_log=None / record_change raises / late binding）· role_name propagation · AnalystAgent 整合（PARAMETER_CHANGE + STATE_CHANGE 路徑）。

**E2 審查**：APPROVE_WITH_NITS（5 非阻塞 nits — log spam throttle / 未知 event_type 測試 / thread-safety doc / TODO.md 條目 / 文字輕微 drift）。

**回歸**：pytest **2820 passed** / 2 pre-existing DYNAMIC-RISK fail / 14 skipped（1567 → **2820**，+12 from FN-3 + 其他 Phase D-E 外盤）。

---

### DUAL-TRACK-EXIT-1 Step 0 + MARKET-KLINES-STALE-1 fix + EXIT-FEATURES-TABLE-1 skeleton（2026-04-18 · commit 65acde6）

**Step 0 可行性 Sprint 結果**（2/4 綠 + 1/4 黃 + 1/4 紅）→ Phase 1 拆 1a/1b：
- 不確定 1 ✅ estimator CLI 跑通 104 cells（機制綠，bind blocker 獨立）
- 不確定 2 🔴 `decision_features` entry-time snapshot，7 維對齊僅 1/7 直接（`atr_pct`）→ 需新建 `learning.exit_features` + Rust exit handler
- 不確定 3 ✅ ma_crossover live_demo 2.23M / grid_trading live_demo 16.5k；小樣本策略強制 P-only
- 不確定 4 🟡 無 tick 表；kline 1-min 粒度；`market.klines` 自 2026-04-16 21:08 停寫 → fallback #6 事後歸因 audit

**MARKET-KLINES-STALE-1 修復**（root cause = PAPER-DISABLE-1 架構遺漏，非停電事件）：
- `main.rs` 三引擎 `market_data_tx` 全改 `Some(market_tx.clone())`（原 D19 設計僅 Paper 寫入，PAPER-DISABLE-1 後 paper 預設不 spawn 即 DB kline 寫入完全斷）
- `market_writer.rs:180` `ON CONFLICT DO NOTHING` dedup 多 producer 安全（PK `(symbol, timeframe, ts)`）
- Phase 1 ATR 前置 / Phase 1 部署前必修

**EXIT-FEATURES-TABLE-1 骨架**（Phase 1b 前置）：
- `sql/migrations/V999__exit_features.sql`：DDL + 3 索引 + TimescaleDB hypertable，PK `(context_id, ts)`
- `database/exit_feature_writer.rs`：mirror `decision_feature_writer` pattern，+5 單測
- `database/mod.rs`：`ExitFeatureRow` struct（7 維 Track P + exit meta + provenance）
- `tasks.rs::spawn_db_writers` 7→8 tuple，新增 exit_feature writer task
- `event_consumer/types.rs::EventConsumerDeps.exit_feature_tx` 通道
- `event_consumer/mod.rs` destructure with `_exit_feature_tx`（producer 由 Phase 1a 軌道 1 接線）
- `main.rs` 三引擎皆 clone `exit_feature_tx`（避免重蹈 D19 單引擎覆轍）

**Validation**：`cargo check` PASS 0 errors, 0 new warnings。
**Worklogs**：`docs/worklogs/2026-04-18-1--dual_track_exit_feasibility.md` · `docs/worklogs/2026-04-18-2--exit_features_table_design.md`。

---

### EXIT-FEATURES-TABLE-1 Phase 1b producer wiring — `emit_close_fill` 主路徑（2026-04-19 · commit 6ea643e）

**問題**：65acde6 完成 table/writer/channel 骨架但 producer 未接線 → 零 rows 寫入 `learning.exit_features`。

**修復**（`emit_close_fill` 主路徑接線）：
- `paper_state` 新增 `PositionExitSnapshot`（value-typed 結構），在 close 前捕獲關倉前狀態（open_price / pnl / size / entry_context_id 等），避免 mutate state 後取值失真。
- `PriceHistoryTracker::compute_roc(lookback_ms)` 新增 per-symbol 短窗 ROC。
- `tick_pipeline/mod.rs::build_exit_feature_row` 構造 7 維 Track P 維度（est_net_bps / peak_pnl_pct / atr_pct / giveback_atr_norm / time_since_peak_ms / price_roc_short / entry_age_secs）+ exit meta（strategy_name / close_tag / exit_source / exit_trigger_rule）+ provenance（context_id / engine_mode / feature_schema_hash）。
- `compute_feature_schema_hash()` 加 `OnceLock` 緩存（per-process 一次性計算）。
- `emit_close_fill` path：捕獲 snap → 構造 row → `try_send` 到 `exit_feature_tx`（fail-soft：channel 未接或 slot 滿時靜默 no-op）。
- `parse_exit_tag` 自由函式：`{risk_close|stop_trigger|strategy_close}:<reason>` → canonical `(exit_source, exit_trigger_rule)`。

**Tests**（+15 新測試）：7 維構造正確性 / parse_exit_tag 全分支 / fail-soft 語義 / feature_schema_hash 穩定 / ROC 缺資料退回 0 / snap 捕獲時序正確性。**Pre-existing 5 個 `test_exit_feature_row_*` WIP 仍 fail**（2 個漏接 close paths，由後續 `c7171b2` FUP 修復）。

**覆蓋**：`emit_close_fill`（strategy close 主路徑，paper/demo/live 三引擎共用）。
**未覆蓋**（→ c7171b2 FUP）：`process_external_fill`（IPC 外部 fill 報告）· `ipc_close_symbol` paper 分支（operator /close_symbol API + dust eviction + orphan_handler→Paper）。

---

### FILL-CONTEXT-LINKAGE-1 — 訊號時刻 context_id 端到端傳遞（2026-04-19 · commit bd45e90）

**問題**：P1-7 C ML 訓練無標籤可用。`learning.decision_features`（3.36M rows）與 `trading.fills.entry_context_id`（3514 rows）JOIN **0 overlap**，`edge_label_backfill.py` 找不到可標籤的 fills。

**RCA**（B 路徑 — operator 拒絕 dry-run / archive，要求架構級修復）：
- `decision_features.context_id` 由 `decision_context_producer.rs:144` 在 **訊號時刻** 用 `make_context_id(em, &event.symbol, event.ts_ms)` 寫入。
- `trading.fills.entry_context_id` 由 `tick_pipeline/commands.rs:apply_confirmed_fill` 在 **WS exec time** 用 `make_context_id(em, symbol, ts_ms)` 寫入，`ts_ms = exec_ts`（漂移 100-500ms）。
- 同 formula 不同 `ts_ms` → 不同字串 → 永遠 JOIN 失敗。
- Bug 僅影響 exchange branch；paper branch（`on_tick.rs:1140`）兩端都用 `event.ts_ms` 已對齊。

**修復**（端到端傳遞訊號時刻 id）：
- `OrderDispatchRequest.context_id: String`（`tick_pipeline/mod.rs:551`）新欄位
- `PendingOrder.context_id: String`（`event_consumer/types.rs:50`）新欄位
- `apply_confirmed_fill(..., signal_context_id: &str, ..., order_link_id: &str)` 新參數
  - 兩個原本用 `make_context_id(em, symbol, ts_ms)` 重算的點（line 401 `set_entry_context_id` + line 455 `TradingMsg::Fill.context_id`）改用 `signal_context_id`，empty 時 fallback exec-time 重算（保留 orphan/shadow 舊行為）。
- 3 close-dispatch sites（`execute_position_close` / `ipc_close_all` / `ipc_close_symbol` exchange 分支）帶 `paper_state.get_entry_context_id(symbol).unwrap_or("").to_string()` 確保 close fill 的 entry_context_id 與當初開倉 stamp bit-identical。
- `event_consumer/dispatch.rs` 鏡射 `req.context_id` → `PendingOrder.context_id`；`event_consumer/mod.rs:883` 傳 `&po.context_id` 到 `apply_confirmed_fill`。

**Tests**：
- `apply_confirmed_fill_preserves_signal_context_id`：seed `event.ts_ms=1000`，呼叫 `apply_confirmed_fill(...,ts_ms=2000, signal_context_id="ctx-demo-BTCUSDT-1000",...)`，斷言 `paper_state.get_entry_context_id("BTCUSDT") == Some("ctx-demo-BTCUSDT-1000")`（訊號時刻 id），且 `!= Some("ctx-demo-BTCUSDT-2000")`（pre-fix exec-time 字串絕不出現）。
- `apply_confirmed_fill_falls_back_when_signal_id_empty`：傳空字串時退回 exec-time 重算 `ctx-demo-BTCUSDT-2000`。

**Workflow**：sub-agent 寫碼 → trust-but-verify diff inspect → 識別出 EXIT-FEATURES Phase 1b FUP scope creep → operator 選 B 路徑 hunk-split → Python script 自動 partition unified diff（per-hunk old-line-number classification）→ 兩 commit 獨立 cargo test 綠 → 兩 commit 落地。

**測試**：engine lib 1560→**1564 passed / 0 failed**（+2 regression tests）。
**部署**：待 `restart_all.sh --rebuild`；解鎖 P1-7 C 訓練（待累積 ≥7d 新流量讓 JOIN-able rows 形成）。

**檔案**（9 changed, +226/−6）：
- `tick_pipeline/mod.rs`（OrderDispatchRequest 欄位）
- `tick_pipeline/commands.rs`（apply_confirmed_fill 簽章+body + 3 close-dispatch sites）
- `tick_pipeline/on_tick.rs`（exchange open + paper shadow 注入 context_id）
- `tick_pipeline/tests.rs`（2 regression + 3 既有 OrderDispatchRequest literal 補欄位）
- `event_consumer/{types,dispatch,mod,tests,handlers/tests}.rs`（PendingOrder 欄位 + 3 test sites）

---

### EXIT-FEATURES-TABLE-1 Phase 1b FUP — 2 個漏接 close paths 補完（2026-04-19 · commit c7171b2）

**問題**：Phase 1b producer wiring（commit `6ea643e`）完成 `emit_close_fill` 主路徑，但留 5 個 `test_exit_feature_row_*` WIP 測試失敗 — 揭露 2 個 close-fill paths bypass 了 `learning.exit_features` 寫入：
1. `process_external_fill`（commands.rs:~150）— IPC 外部 fill 報告（orphan handler / exchange reconciler）
2. `ipc_close_symbol` paper 分支（commands.rs:~700）— operator `/close_symbol` API + dust eviction + orphan_handler→Paper 模式

Track P 標籤覆蓋因此不完整；ML 訓練會見到從這兩個 route 的 closes 沒有 exit_features rows。

**修復**：
- 抽出 `try_emit_exit_feature_row(&self, ...)` `pub(crate)` helper（`tick_pipeline/mod.rs`）— 從 `emit_close_fill` inline body 提取，identical fail-soft 語義（snap=None 或 exit_feature_tx 未接 → 靜默 no-op）。
- `process_external_fill`：`apply_fill` mutate state 前先捕獲 `position_exit_snapshot`；on close（`realized_pnl != 0`）emit 一列；策略名 verbatim 傳遞（`parse_exit_tag` 對未知 prefix → ExternalFill category）。
- `ipc_close_symbol` paper 分支：`close_position_at_market` 前先捕獲 snap + entry_context_id + 預關 qty/price；on success emit `strategy_close:ipc_close_symbol` tag with `exit_source=Risk` / `exit_trigger_rule=ipc_close_symbol`。

**Tests**（+3）：
- `test_ipc_close_symbol_paper_emits_exit_feature_row`：full wiring end-to-end 驗證 IPC paper close emit 一列含正確 context_id + strategy_name + exit_source。
- `test_try_emit_exit_feature_row_helper_direct_call`：helper 直接呼叫 + 自訂 close_tag 經 `parse_exit_tag` 正確分類為 ExternalFill。
- `test_try_emit_exit_feature_row_fail_soft`：snap=None 或 tx 未接 → no-op 不 panic 不 emit。

**Workflow**：發現過程 = sub-agent 為達成「all green」自動補完了 Phase 1b FUP（scope creep beyond FILL-CONTEXT-LINKAGE-1）；operator 選 B 路徑 hunk-split → 兩個 ticket 獨立 commit / bisect-friendly。

**測試**：engine lib 1564→**1567 passed**（pre-existing 5 個 WIP `test_exit_feature_row_*` 全綠化）。
**檔案**（3 changed, +206/−10）：
- `tick_pipeline/mod.rs`（try_emit_exit_feature_row 抽出）
- `tick_pipeline/commands.rs`（2 paths 接線）
- `tick_pipeline/tests.rs`（+3 tests）

---

### E5-FN-2 — `ai_budget` request_id dedup 防雙重計費（2026-04-19 · commit fd480ba）

**問題**（Audit §七 7.2 · R6/P2 · financial integrity）：`learning.ai_usage_log` PK `(time, scope, request_id)` 用 `time=NOW()`，transient DB partial-failure 後 retry 會拿到新的 `NOW()`，PK 無法 dedup → 同一次 AI call 可能計費兩次，silently 超支月預算，違背憲法原則 #13（cost-edge awareness）。

**三段式修復**：
1. **V018 migration**：`learning.ai_usage_log` 新增 partial UNIQUE index on `request_id`（`WHERE request_id <> ''`），legacy V010 `''` 預設保持有效，新 rows dedup；operator 手動 apply，engine binary forward-compatible；idempotent `IF NOT EXISTS`。
2. **`usage_io::insert_usage`**：`ON CONFLICT (request_id) WHERE request_id <> '' DO NOTHING` + `RETURNING 1`，caller 無需第二次 round-trip 即可區分 first-insert vs dedupped retry；返回 `bool`。
3. **`tracker::record_usage`**：`insert_usage` 返回 `Ok(false)` 時跳過 in-memory MTD cache increment（避免 scope 雙重扣費）；新增 `BudgetTracker::make_request_id(scope)` helper 鑄造 canonical id `{scope}-{ts_ms}-{rand_hex8}`（decimal ms + 8-char lowercase hex 防 intra-ms 碰撞）。

**Callers 更新**：
- `claude_teacher/mod.rs`：替換 `format!("teacher-{}", now_ms())`（同 ms 會碰撞）為 canonical helper。
- `ipc_server/handlers/budget.rs::handle_record_ai_usage`：Python caller 省略 request_id 時鑄造新 canonical id，取代硬編碼 `"py-sync"`（否則 V018 index 下 **每個** Layer-2 sync 都會碰撞而 silently drop 成本 rows）。

**Tests**（+5 in `ai_budget::tracker`）：
- `E5-FN-2-A`：`make_request_id` 格式合規（3 segments / 8-char lower hex / realistic ts_ms / 正確 scope prefix）
- `E5-FN-2-B`：1000 back-to-back mints 全部 distinct（birthday-collision-safe）
- `E5-FN-2-C`：first-insert path byte-identical to pre-fix cold-start 行為
- `E5-FN-2-D`：cold-start cache 在 3 個 distinct request_ids 下仍然累加
- `E5-FN-2-E`：Layer-2 default mint 唯一（no `py-sync` literal regression）

**測試**：engine lib 1567→**1572 passed**（+5 E5-FN-2）· `ai_budget` module 25→30 all green · `claude_teacher` 61 passed（caller 無 regression）· Python `ai_budget_routes` 7 passed（API proxy 未動）。

**部署 order（operator 注意）**：
1. 先 apply migration：`psql $DATABASE_URL -f sql/migrations/V018__ai_usage_log_request_id_unique.sql`
2. 再重建 engine：`bash helper_scripts/restart_all.sh --rebuild`
   順序重要：binary 早於 index 上線則 `ON CONFLICT` 會 target 不存在的 constraint 而 INSERT 全部報錯。migration 冪等，重跑無害。

---

### E5-FN-3 — `agent_audit_bridge` + AnalystAgent pilot wiring（2026-04-19 · commit 19f3d85）

**RCA**（驗證 Audit §七.7.3 聲稱）：5-Agent 系統（Scout / Strategist / Guardian / Analyst / Executor）共 4 agent 有 19 個 `self._audit(event_type, data)` call-sites（Scout 為 0），但 `strategy_wiring.py` 建構每一個 agent 都 **未傳 `audit_callback=`** → `BaseAgent._audit_callback=None` → 19 次呼叫全部 silently no-op。直接 grep 確認 5 個 agent 檔 **零** `change_audit_log` 寫入 — 違反 Root Principle #8「交易可解釋」。`governance_hub` 等提供的審計來自 state machines（authorization / risk_governor / decision_lease / reconciliation），**非** agent decision points。

**設計**：新 `agent_audit_bridge.py` 模組匯出 `make_agent_audit_callback(gov_hub, role_name) -> Callable[[str, Any], None]`：
- Signature 與 `BaseAgent._audit` 完全一致，**零 agent 程式碼修改**。
- Events 分類：decisions（verdict / edge_evaluation / intent_produced / trade_analyzed）→ `PARAMETER_CHANGE`；`*_received` / `directive_received` → `STATE_CHANGE`。
- 每次呼叫 lazy-read `gov_hub._change_audit_log`（支援 late binding）。
- 3 層 fail-open：`gov_hub=None` / `audit_log=None` / `record_change` 拋錯 → 靜默 drop（debug/warning log），絕不 propagate 回 agent 主路徑。
- `auto_approve=True`（agent 決策屬自動）、`who=role_name`、`affected_components=[role_name]`。

**Pilot**：`strategy_wiring.py` Batch 9 + Batch 10 兩個 AnalystAgent 建構現在傳 `audit_callback=_ANALYST_AUDIT_CB`，由 `GOV_HUB` 經橋樑建。遵循 Batch 12 已建立的 `_paper_live_gate_audit_cb` 同樣 pattern。

**Tests**（+12 all green）：factory contract / event 分類 / 多事件持久化 / fail-open 4 分支 / Pilot 整合（AnalystAgent `analyze_trade` → +1 audit row `who="AnalystAgent"` + `PARAMETER_CHANGE` + `AUTO_APPROVED`）/ Pilot 整合（`EXECUTION_REPORT` receipt → `STATE_CHANGE` row）。

**§九 singleton 登記**：`_ANALYST_AUDIT_CB` / `_GOV_HUB_FOR_ANALYST` 登入 `strategy_wiring.py`；`agent_audit_bridge` 本身無狀態工廠，不持 singleton。

**APPROVE_PARTIAL follow-up → TODO `E5-FN-3-FUP`**（4 agent 待 wire）：
- `StrategistAgent` (`strategy_wiring.py:172`) — 7 個 existing `_audit` calls，只需注入 callback
- `GuardianAgent` (`strategy_wiring.py:215`)
- `ExecutorAgent` (`strategy_wiring.py:345`)
- `ScoutAgent` (`strategy_wiring.py:114` + `multi_agent_framework.py:410`) — 需新增 `_audit` calls at `produce_intel()` / `produce_event_alert()`（Scout 目前 0 audit calls）。

**Regression**：`control_api_v1` suite **2451 passed** / 2 pre-existing DYNAMIC-RISK fail / 1 skipped；其中 `test_batch9_perception_analyst_integration` / `test_change_audit_log` / `test_governance_hub` / `test_analyst_agent_unit` / `test_integration_phase2` 全綠。

**Refs**：CLAUDE.md §二 Root Principle #8 · DOC-06 §5 · EX-06 §1。

---

### E5-P2 Refactor Wave 2 — 2 delivered / 3 evidence-based CANCEL / 2 defer（2026-04-19 · commits 11dedbf / 822f799）

**workflow**：PA 派發 5 × general-purpose sub-agent（`isolation: "worktree"`，`run_in_background: true`）→ 2 delivered + 3 evidence-based CANCEL → Phase C 2× 並行 E2 code-review → 2/2 APPROVE_WITH_NITS（零 REJECT，所有 nit 非阻塞）→ Phase D 全量回歸（Rust engine lib 1560 passed / 2 pre-existing EXIT-FEATURES-TABLE-1 WIP fail，非 E5-P2 regression）→ Phase E 收口。

**defer**（`tick_pipeline/mod.rs` EXIT-FEATURES-TABLE-1 pre-existing WIP +45 行衝突）：
- **P2-1** PipelineCommand enum reorg — 與 P2-6 共爭 tick_pipeline/mod.rs
- **P2-6** fill_context_builder.rs 抽取 — 同上

**delivered**：

- **P2-3 rename multi_interval_ws → multi_interval_topics**（`11dedbf`）— 3 files changed（rename + 2 import sites）；移除零 caller `configure_multi_interval(ws, symbols)`（斷 WsClient 耦合，完成 pure-function 抽取意圖）；+2 新 contract tests（`test_full_subscription_list_ordering_contract` 釘 kline-first 5-element 順序 + `test_multi_symbol_subscriptions_grouping_contract` 釘 per-symbol grouping）；MODULE_NOTE 中英重寫宣告「pure topic builder, no WsClient」；docs/references/2026-04-04--bybit_api_reference.md §2.1 同步更新（E2 nit 處理）。

- **P2-4 strategies magic numbers → config**（`822f799`）— 3 files changed（+366 / -7）；7 literals 遷移：`bb_breakout` `hurst_regime_boost=0.1` / `exit_bonus_trailing_stop=0.2`（shared 2 sites） / `exit_bonus_regime_shift=0.1` / `exit_bonus_pctb_revert=0.05` / `exit_penalty_bw_squeeze=-0.05`；`grid_trading` `cooldown_ms=60_000` 連帶封死 TOML 不可達 latent gap（`pub(crate)` 提權 + `create_with_params` factory wire + `#[serde(default)]` 熱重載 back-compat）；+9 bit-exact default unit tests（literal→literal 逐欄比對）；sentinel `default_qty=1e9` + architectural invariant `confluence max=65` 明確排除。

**CANCEL（evidence-based，per `feedback_pushback.md` 與 E5 審查鏈精神）**：

- **P2-2 onnx_inference consolidate**：優化前提（`model.inputs[0].name.clone()` per-inference 配置）已由 EDGE-P3-1 Phase B Step 7b 滿足 — `edge_predictor/ort_backend.rs:177-189` 載入時一次 clone `input_name: String`，inference 用 `.as_str()` 零分配；`ml/model_manager.rs` 仍是 stub（line 108 `TODO: Replace with ort::Session::run()`）無第二個 ort session 可合併；7 integration tests 在 `tests/edge_predictor_ort_backend.rs` 依 `edge_predictor::ort_backend::OnnxTrioPredictor` 路徑 — 純搬遷成本 > 0，效益 0。

- **P2-7 claude_teacher/directive_handler 抽取**：applier.rs 560 LOC production / 1068 含 tests（FIX-08 commit 50d7a4b 已把 fixtures 拆到 `applier_test_fixtures.rs`）；parsing 早在 `parser.rs` 分離；`P0_P1_DENYLIST_FIELDS` + `find_denylisted_field` helper + 4 `apply_*` methods 1-to-1 耦合；MODULE_NOTE 明確「this module is the **only** path that turns a parsed `Directive` into a side-effect」為 R6 CRITICAL 單一入口 invariant；分拆要求 `pub(super)` 洩漏內部卻無外部消費者受益。

- **P2-8 Python learning_batch_writer**：`control_api_v1/app/` 全樹**唯 1** `INSERT INTO learning.*` 在 `ai_service_feedback.py:105` → 單點無法「consolidate」；`ml_training/*.py` 11 個 writer 各寫 distinct schema（weekly_review_log/cpcv_results/james_stein_estimates/linucb 3 變體/foundation_model_features/dl3_ab_decisions/bayesian_posteriors/ml_parameter_suggestions/pattern_insights）共享 row shape 為零，去重退化到 `cur.executemany(sql, rows)`；跨進程連線慣用語各有原因（cron `_get_db_conn()` / CLI `dsn: str` / FastAPI `db_pool.get_conn()`）統一會強拖 pool 狀態進 cron scripts；真實批寫入重複已由 E5-P0-4 `database/batch_insert.rs` Rust 側解決（b66a8aa）；audit §五 未列此項，僅 §九 blueprint 前瞻提及。

**Follow-up**：
- **E5-P2-4b**（P2）：`strategies/bb_breakout.rs` 1265 / `strategies/grid_trading.rs` 1434 / `strategies/mod.rs` 1442 均超 §九 1200 硬上限（非 Wave 2 新增，pre-existing tech debt），分檔拆解獨立排期。
- **P2-2/P2-7/P2-8**：audit §九 blueprint 對應行建議下修或刪除（證據已封存於本條目）。
- **P2-1/P2-6**：EXIT-FEATURES-TABLE-1 WIP 落地後重新評估。

**Nits（非阻塞）**：
- P2-3：`docs/references/2026-04-04--bybit_api_reference.md:915,940,944` 舊檔名 + 已刪 `configure_multi_interval` 引用 — Phase E 同時修正。
- P2-4：commit message 宣稱 "f64::to_bits" 實則 `(a - b).abs() < f64::EPSILON`（literal→literal 等效但措辭略強）；E5-P2-4 JSON substring match `"\"hurst_regime_boost\":0.22"` 對 serde 未來 formatting 變化脆弱（不阻塞）。

---

### E5-P1 Refactor Wave 1 — 6 delivered / 2 evidence-based cancel（2026-04-19 · commits ba8cd2c / 76cd793 / d6f7572 / b0dc6b6 / c220375 / 1b72f90）

**workflow**：PA 派發 8 × general-purpose sub-agent（`isolation: "worktree"`，`run_in_background: true`）→ 6 delivered + 2 evidence-based cancel → Phase C 6× 並行 E2 code-review → 全 APPROVE / APPROVE-WITH-NITS（zero REJECT）→ Phase D 全量回歸（Rust 1533 / Python 2511）→ Phase E 收口（本 commit）。

**Delivered（6）**：

- **P1-1 paper_state 拆** — `ba8cd2c` / worktree `agent-a65a32da`。2380-line monolith → 8 submodules（`mod.rs` 154 · `containers.rs` 60 · `accessor.rs` 339 · `owner_attribution.rs` 221 · `fill_engine.rs` 475 · `snapshots.rs` 86 · `dust_gate.rs` 129 · `tests.rs` 1187），production 全在 800 warn 線下；+3 bit-exact f64 oracle tests（`close_pnl` · `entry_notional_accumulate` · `weighted_avg_entry`）以 `f64::to_bits()` 對齊。所有外部呼叫者通過 `mod.rs` `pub use` re-export 保留；`pub(super)` 限制兄弟 module 範圍。MICRO-PROFIT-FIX-1 `entry_notional` 累加 + P0-6 `dust_frozen` + P1-8 FUP `<` dust boundary + ORPHAN-ADOPT-1 `positions_mirror` side-car 全部 invariant 保留。E2 APPROVE（1 cosmetic commit-msg nit）。
- **P1-3 handlers by-domain 拆** — `76cd793` / worktree `agent-a7e5b11b`。`event_consumer/handlers.rs` 1722 → 5 production files（`lifecycle` / `strategy_params` / `risk` / `edge_predictor` / `mod.rs`）+ `tests.rs`；`ipc_server/handlers.rs` 1169 → 7 production files（`misc` / `budget` / `teacher` / `strategy` / `risk` / `dynamic_risk` / `governance`）+ `mod.rs`。26 `PipelineCommand` arms + 22 IPC method-strings 完全 1:1 保留；`pub(super)` / `pub(in crate::ipc_server)` 精準 scope，無 `pub` 廣化。E2 APPROVE（zero nit）。
- **P1-4 BaseAgent + llm_call_wrapper** — `b0dc6b6`。5 agents（Scout / Strategist / Guardian / Analyst / Executor）共用 ~80 行 surface 抽到 `base_agent.py`（`start/pause/stop`、`_audit()` 角色前綴via `self.role.value`、`_record_llm_call()`、`get_stats()`）+ `llm_call_wrapper.py`（`ollama_is_available` + 4 call helpers）。Audit 事件前綴 byte-identical；Ollama kwargs（`temperature=0.3`、`max_tokens=1024`、`think=True`）保留；fail-closed heuristic fallback 路徑不變；循環 import 通過函數內 lazy `import` 化解；零新 singleton。E2 APPROVE（dead-on-arrival `call_ollama_timed` helper 待 follow-up 接線）。
- **P1-5 JSON-RPC cross-layer helpers** — `c220375`。4 orphan helper modules：`ipc_error_handler.py`（199 LOC，HTTP 504/503 分類 + `raise_http_for_ipc_error`）· `ipc_dispatch.py`（242 LOC，`one_shot_ipc_call` + `get_or_connect_shared_client` lazy slot singleton）· `param_extractor.rs`（345 LOC，9 `require_*`/`optional_*` helpers + 15 unit tests，`#![allow(dead_code)]` 等 handlers 遷移跨 wave 避衝突）· `supervised_spawn.rs`（214 LOC，`spawn_cancellable_interval` + `on_cancel_msg` `&'static str` 選項保留 legacy cancel 訊息）。4 proof-of-adoption migrations：`ai_budget_routes` 30 行 try/except → 1 call · `live_session_routes._ipc_command` 保留 `"503: IPC command '<m>' failed: ..."` byte-identical · `tasks::spawn_fee_rate_tasks` + `spawn_instrument_refresh`。E2 APPROVE-WITH-NITS（cancel-log 多 `task=<name>` structured field；CLAUDE §九 singleton 表補 `_SHARED_IPC_SLOTS`；`param_extractor` → handlers 遷移 follow-up TODO）。
- **P1-8 rejection_coding** — `d6f7572` / worktree `agent-ab2a7cfd`。`intent_processor/rejection_coding.rs` 549 LOC；15 `RejectionCode` variants 枚舉所有 intent 拒絕訊息（`GovernanceNotAuthorized` / `DuplicatePosition` / `InsufficientBalance` / `GuardianRejected` + `from_guardian_review` 保留 `{:?}` Debug fmt over `Vec<String>` / `QtyZero` 含 `$` sigil / `RiskGate` upstream passthrough / `GlobalNotionalCap` / 7× `CostGateJs*` incl 中英文混排 + em-dash `—` byte-identical）；18 call sites 遷移（router.rs 11 / gates.rs 6 / mod.rs 1 @ 387）；+16 literal-match 單測非 tautological。`.contains("cost_gate")` / `.starts_with("qty_zero:")` 歷史斷言無需調整。E2 APPROVE（第二 `impl` block + `#[allow(dead_code)]` 分類 helpers 待 consumer 接線後移除）。
- **P1-9 + P2-5 governance_hub Mixin 拆 + @deprecated** — `1b72f90`。策略 = Mixin via multiple inheritance（companion to existing `GovernanceHubStatusCascadeMixin` FIX-08）。MRO `[GovernanceHub, StatusCascadeMixin, EventHandlersMixin, object]`；新 `governance_hub_event_handlers.py` 237 LOC 容納 5 handlers（`_make_audit_callback` / `_make_incident_callback` / `_wire_callbacks` / `_invalidate_auth_cache` / `_check_de_escalation_gate`）。P2-5 併入：5 methods `typing_extensions.deprecated`（中英雙語 warning message，runtime 路徑 byte-identical）：`check_learning_tier_capability` / `is_enabled` / `get_risk_level` / `check_risk_and_act` / `trigger_risk_upgrade`（`guardian_agent.py:534` 仍呼叫此末項，DeprecationWarning 期中產生 +8 warnings）。`governance_hub.py` 1052→1005 LOC；singleton identity 保留；所有 `getattr(hub, "_invalidate_auth_cache")` 外部呼叫（`live_trust_routes.py:421`、`live_session_governance.py:114,165`）依 MRO 解析不變。E2 APPROVE（commit-msg 行號 off-by-12 + 1 `noqa: F841` 註釋性 lint）。

**Evidence-based cancel（2）** — sub-agents 按 `feedback_pushback.md` 推回錯前提：

- **P1-6 gate_pipeline — CANCEL**：`h0_gate.py` vs `paper_live_gate.py` 實測 **0 行真實重複** —— H0 = `<1ms` SLA fail-fast 熱路徑 5 連鎖 checks；PaperLive = batch 模式 11 criteria + operator-approval FSM + JSON export。`GateCheckResult` 與 `H0GateCheckResult` 結構共用 0。套任何 pipeline 抽象既威脅 H0 延遲又威脅 paper_live audit-byte 合約；加 indirection 換 0 dedup。建議 cancel，僅當未來出現第三個類似 gate 再重開。
- **P1-7 command_dispatch — CANCEL**：任務前提過時 —— `PipelineCommand` dispatch-match **已在 prior pass** 從 `tick_pipeline/mod.rs` 遷至 `event_consumer/handlers.rs:274-1041`（`handle_paper_command`，767 行），而 `event_consumer/` 本在本任務 DO-NOT-TOUCH list 上。`tick_pipeline/commands.rs` 實際是 13 helper methods 的 `impl TickPipeline` block，不是 dispatch。surface 一個新候選任務「切 `commands.rs` 836 LOC 成 `commands/orders.rs` / `commands/governor.rs` / `commands/close.rs`」——獨立工項，非本任務。

**Sub-agent refuse pattern 第三次驗證**：2026-04-07 觀察的 write-after-read refuse 在 2026-04-18 E5-P0 Phase A probes + 2026-04-18 DUAL-TRACK 雙寫 + 2026-04-19 E5-P1 Wave 1（8 次並行 + 2 次 Wave 2 pending）中穩定不復現。6/8 寫碼成功，2/8 是 evidence-based refusal（非 prompt-injection-refuse），pattern 完全可預測可派發。

**測試基準線**：Rust engine lib 1498 → **1533 passed / 0 failed**（+35 new：P1-1 +3 · P1-5 +17 · P1-8 +16 - 1 shift）；Python pytest 全量 **2511 passed / 2 pre-existing DYNAMIC-RISK-STATUS-TEST-SIG-1 fail / 1 skipped / 407 warnings**（+8 DeprecationWarnings 預期）；zero new regression。

**整合路徑**：3 items（P1-4 b0dc6b6 · P1-5 c220375 · P1-9 1b72f90）由 sub-agent 直接在 main tree commit（外部 worktree 因 Python cross-module 跨層改動範圍廣，worktree 複製成本高於 main tree 提交）；其餘 3 items（P1-1 cd0deb9 · P1-3 6f5b9bb · P1-8 a9a7f67）留在 worktree → 主 session stash WIP → 3 次 cherry-pick `cd0deb9 6f5b9bb a9a7f67` 全 clean auto-merge 無衝突（僅 `database/mod.rs` ordering 良好預測）→ Rust `cargo check --lib` 0 new warning → `cargo test --lib` 1533 passed 0 fail → pytest 2511 passed → 部署 `restart_all.sh --rebuild`。

**nits rolled into Phase E（本 commit）**：
- CLAUDE.md §九 singleton table 補 `_SHARED_IPC_SLOTS` / `_SHARED_SLOT_LOCK` → ipc_dispatch.py（E5-P1-5 E2 nit）
- CHANGELOG 本段原始 claim「cancel-log byte-for-byte」實際新增 `task=<name>` structured field；message text 保留但可觀測性增強（E5-P1-5 E2 nit，已在上段修正表述）
- param_extractor.rs `#![allow(dead_code)]` → 待 handlers.rs 遷移消費，follow-up TODO 待另行排
- P1-4 `call_ollama_timed` helper dead-on-arrival 待接線（E5-P1-4 E2 nit）
- P1-8 第二 `impl RejectionCode` block 可折疊 + `#[allow(dead_code)]` 分類 helpers 待 consumer 接線後移除（E5-P1-8 E2 nit）

**後續**：Wave 2（7 P2 items，P2-5 已併入 P1-9）待本 commit 整合部署後並行派發。E5-P1-2 `main.rs` bootstrap 拆分依 audit 建議「觀察穩定性再拆」暫不派，operator 可顯式覆蓋。

---

### P1-16 HALT-SESSION CROSS-SYMBOL PRICE CORRUPTION — 雙軌修復（2026-04-18 · commit fef688e）

**問題**：Rust halt_session force-close 路徑將 triggering tick 的 symbol 價格跨 symbol 汙染到所有其他 symbol 的 close fill。pairer 用被汙染的 exit_price 計算 bps，疊加 partial-match 微分母放大，產生 `-17,617,373 bps` 極端值。demo `edge_estimates.json` `grand_mean=-2214 bps` 真正元兇。下游 P1-15 清 phantom cells + P1-17 Winsorize ±5000 bps 只是 safety net，未修根因。

**上游修復（主）** — `rust/openclaw_engine/src/tick_pipeline/on_tick.rs:1461-1516`
- `RiskAction::HaltSession(reason)` 分支由手寫 `self.latest_prices.get(sym).copied().unwrap_or(event.last_price)` + `close_position` + 手動 `dynamic_risk_sizer.record_closed_trade` 改為呼叫既有安全 helper `close_position_at_symbol_market`（與 `ClosePosition` 分支 line 1438-1454 同 pattern）
- helper 內部優先取 per-symbol `latest_prices`，缺失時 fallback 到 `entry_price`（不是 triggering tick）；`record_closed_trade` 由 helper 條件性呼叫（跳過 zero-PnL 合成值避免 Sharpe 污染）
- 新單測 `test_halt_session_uses_per_symbol_price_not_triggering_tick`：3 symbol（BTC/ETH/DOGE）apply_fills at 50_000/3_000/0.20，NAN'd ETH/DOGE 的 `latest_prices`，charged $2500 → drawdown 25% > 15% halt 閾值，tick BTCUSDT @ 50_500。斷言 BTC close=50_500、ETH close=3_000（fallback 非 50_500）、DOGE close=0.20。

**下游防禦（備）** — `program_code/ml_training/realized_edge_stats.py` `_pair_round_trips`
- Gate (a) price-jump skip：`|ln(exit/entry)| > 0.5` → log + counter + skip。斷絕任何 P1-16-like cross-symbol 汙染穿透到 bps 統計。
- Gate (b) 分母保護：entry dict 新增 `qty_total`，計算 `entry_notional_full = entry_price * qty_total`，`denom_bps = max(entry_notional_full, match_notional)` 用於 `_bps()` 呼叫（含 entry_fee_bps / exit_fee_bps）。防 partial-match 微分母放大。`notional_usd` 欄位仍用 `match_notional` 保留透明度。
- 新常數 `_PRICE_JUMP_LN_LIMIT = 0.5`、全域計數器 `_price_jump_skip_count`、helper `_is_price_jump_pair`、`_reset_price_jump_counter()`、`get_price_jump_skip_count()`。
- 5 新單測：`test_price_jump_constant_is_half` / `test_price_jump_helper_flags_extreme_ratio` / `test_price_jump_skips_p116_style_cross_symbol_pair`（DOT $7.80→$2357.94 即 P1-16 指紋）/ `test_price_jump_allows_legitimate_large_move`（60%，|ln|=0.470<0.5 穿透到 Winsorize）/ `test_denominator_protection_uses_full_entry_notional_on_partial_match`（10/100 qty partial → -500 bps 非 -5000）。`test_extreme_positive_roundtrip_clamps_to_ceiling` / `test_boundary_exactly_negative_limit_passes_through` 的 exit price 由 110000/5000 調整為 14000/8500 以避開 price-jump gate 直達 Winsorize 邊界。

**實證**：archived demo 6616 條 `engine_mode='demo_archive_20260418'` fills → 5129 round-trips → **27 skips / 0 clamps / mean -9.02 bps（vs 修前 -2214 bps，245× cleaner）**。

**測試基準線**：engine lib 1497 → **1498 passed**（+1）；`ml_training/tests/test_winsorize.py` **238 passed**（+5）。

**部署**：`restart_all.sh --rebuild` 進行中。

**後續**：P1-17 Winsorize ±5000 bps 由「主線矯正」回退為「safety net」；live_demo 7d 乾淨 baseline `grand_mean=-14.97 bps` 作為首個真實 edge 觀測；demo 重啟後累積 1–2w 乾淨 fills → P0-3 edge 重評。

---

### E5-P0 Refactor Wave — 5 P0 並行合流（2026-04-18 · commits 6798ce1…c9c3ad8）

**工作流**：PA → FA（5× Explore sub-agent 並行研究，~5 min）→ E1（5× general-purpose sub-agent isolated worktree 並行寫碼，~60 min）→ E2（5× sub-agent 並行 code review，~5 min）→ E4（cargo test + pytest 並行）→ PM 收口。

**sub-agent refuse pattern 解除**：2026-04-07 觀察的 8+ 次 refuse pattern 於 2026-04-18 E5 Phase A 夾帶 2 個 write-capability probe 驗證通過（FA-1 Rust / FA-3 Python 均 `probe written: YES`），Phase B 改從主會話 inline 串行升級為 5× sub-agent 並行寫碼（isolated worktree），並於 Phase C 5× sub-agent 並行審查雙重確認。

**5 P0 commit**：
- **P0-3 `common/ws_backoff` + `common/bybit_signer`**（6798ce1）— dedup WS 重連 backoff（`ws_client`+`bybit_private_ws`）與 HMAC-SHA256 簽名（`bybit_rest_client`+`bybit_private_ws`）。保留 `saturating_pow` 語義 + 可注入時間 + lowercase hex + `BybitResult<String>` REST 簽名回傳。+12 單測。
- **P0-4 `database/batch_insert`**（b66a8aa）— 統一 7 writer chunked multi-row INSERT + PG 65535 bind-parameter ceiling 公式 `chunk_rows = (65535 / cols).min(10_000).max(1)` + `exec_single_insert` 單行/fail-soft 包裝。**順帶修 market_writer ticker 4000-row latent bug**（13 cols × 5000 rows = 65000 params 離 PG 硬上限僅 500，加 1 個 schema 欄位即 runtime EB）。+9 單測。
- **P0-1 `state_machine_base` + `MultiObjectStoreMixin`**（d205f03）— 3 state machine 共用抽取（DecisionSM / LeaseSM / ReconcilerSM）。transition_id prefix 保持 byte-exact（atx/ltx/rgt + evt/levt/revt + aud/laud/raud）；observer 回調保留 outside-lock 模式；`IntEnum`/`StrEnum` 並存；RiskGov `_extra_validate()` hook。187/187 SM tests 零變更。
- **P0-2 `strategies/common/` 三模塊**（6777b85）— `PerSymbolState<S>` HashMap wrapper + `TrendCooldown` saturating_sub 冷卻 + `ConfidenceBuilder` ADX+regime 信心公式。**bit-exact f64 preservation** via `f64::to_bits()` oracle test（confidence 公式零漂移）；bb_breakout RC-04 rollback 由快照/恢復強化為原子 struct snapshot。+4 策略文件遷移（+87 行，均 <1200 硬上限）；confluence.rs 未觸。
- **P0-5 `legacy_routes.py` 5 拆 + `auth_routes_common.py`**（c9c3ad8）— 1179 行拆為 auth/gui/system/learning/control 5 個域文件 + 共用 auth helper。**0 module-level singleton capture**（main.py L125-132 monkey-patch 的 8 個符號全部經 `_base = main_legacy` 命名空間 request-time 解析）；**54 路由 diff empty**；`_login_fail_lock` 3 函數原子性保留；`hmac.compare_digest` 常數時間驗證保留；HttpOnly+Secure+SameSite cookie flags 一致；`envelope_response` 集中化（0 hand-wrapped ResponseEnvelope）。

**Phase C 審查結果（5/5 APPROVE）**：
- P0-3: 12/12（HMAC byte-exact，saturating_pow 保留）
- P0-4: 12/12（PG 公式正確，順帶 latent bug fix）
- P0-1: 14/14（observer outside-lock，transition_id byte-exact）
- P0-2: 13/13 APPROVE_WITH_NITS（唯一 nit: 檔案略增 +87 行均 <1200 硬上限）
- P0-5: 16/16（monkey-patch 鏈零破壞，54 路由 diff empty）

**Phase D 回歸**：
- cargo test --lib：**1497 passed / 0 failed**（baseline 1452 + P0-3 +12 + P0-4 +9 + P0-2 +24 ≈ 45 新單測）
- pytest：**2511 passed / 2 pre-existing fail**（commit 81a3807 DYNAMIC-RISK-1 引入的 `TestDynamicRiskRoutes::test_status_*`，E5-P0 stash 驗證同樣 2 fail；獨立開 ticket `DYNAMIC-RISK-STATUS-TEST-SIG-1`，非阻塞 Live）

**Integration path A**：main WIP stash `-u` → 5 cherry-pick 風險遞增序（P0-3 → 4 → 1 → 2 → 5）全 clean auto-merge（僅 P0-4 database/mod.rs 與前值 65acde6 exit_feature_writer mod 宣告 auto-merge 成功，零手動解衝突）→ stash pop 還原 WIP → Phase D 回歸 → PM 收口。

**部署**：`bash helper_scripts/restart_all.sh --rebuild`（含 Rust engine binary + PyO3 + Python 全端重啟）。

---

### MICRO-PROFIT-FIX-1 — 窄帶 cost-edge + fast_track 名義底線（2026-04-17）

**問題**（48h demo 觀察）：
- 989 筆 `fast_track_reduce_half` dust fills — 同倉位被半倉 4-6 次壓到 dust
- 162 筆 COST EDGE 平倉全落 pnl_pct ≈ 0（隨便有盈利就平），形成「微利死循環」

**根因**：
- Fix A gap：fast_track ReduceToHalf 無名義底線，同 symbol 可無限半倉
- Fix B gap：`cost_edge_max_ratio` 預設 0.8 等效未設，任何 `pnl > 0` + 高 cost_ratio 就觸發

**修復（兩個獨立根因，一次部署）**：
1. **Scheme A — 相對名義底線**：新增 `RiskConfig.limits.ft_min_notional_ratio_of_entry = 0.25`，fast_track 過濾掉 `current_qty × price < 0.25 × entry_notional` 的倉位；`PaperPosition.entry_notional` 採 option 2 累加語義（首開 = qty × entry_price，同向加倉累加，減倉不動）
2. **Config Option ② — 窄帶鎖定**：`cost_edge_max_ratio` 預設 0.8 → 0.2，validate 範圍 [0, 100] → [0, 10]；新增 `min_profit_to_close_pct = 0.3`；觸發條件改為 `cost_ratio ≥ max_ratio AND pnl_pct ≥ min_profit`，形成 pnl_pct ∈ [0.3%, 0.55%] 鎖利窄帶（Bybit taker 基準）

**改動（12 檔）**：
- Rust config：`budget_config.rs` · `legacy_migration.rs` · `risk_config.rs` · `risk_config_tests.rs` · `startup.rs`
- Rust 核心：`risk_checks.rs`（`check_position_on_tick` +1 param）· `position_risk_evaluator.rs`（+1 param 全路徑）· `tick_pipeline/mod.rs`（`current_min_profit_to_close_pct()`）· `tick_pipeline/on_tick.rs`（fast_track 名義底線 filter + 窄帶 threading）· `paper_state.rs`（`entry_notional` 欄位 + 5 建構點 + accumulate + migrate helper + 4 新單測）· `ipc_server/tests.rs`（field fix）
- 設定：`settings/risk_control_rules/budget_config.toml`（`cost_edge_max_ratio = 0.2` + `min_profit_to_close_pct = 0.3`）
- 測試：`tests/micro_profit_fix_integration.rs`（7 新整合測試）

**熱重載保證**：3 參數全部經 ConfigStore/ArcSwap 熱讀，TOML 僅 cold-start default。舊快照 `cost_edge_max_ratio = 100.0` 由 `sanitize_legacy_budget_config` 原地 clamp 成 0.2（warn! 日誌 + validate 通過），`startup.rs` 改為「parse-no-validate → sanitize → validate」順序。

**測試**：
- engine lib 1413 (default) / 1420 (edge_predictor_ort) 全綠（+62 / +72 vs 1351/1348 baseline，含 P1-8 合流的測試）
- core 380 · phase4_integration 3 · reconciler_e2e 19 · stress_integration 35 · rrc1_audit_tests 4
- `micro_profit_fix_integration.rs` 7/7 passed（新增）
- `paper_state::tests::test_entry_notional_*` 4/4 passed（新增）

**E2 審查**：APPROVED_WITH_NITS（3 個非阻塞 nits：`migrate_legacy_entry_notional` 未接入 startup（defence-in-depth hook）；`export_state` 使用 struct update 語法透傳 entry_notional；legacy fail-open 路徑無專測）。

**預期效應（24-48h 觀察指標）**：
- `fast_track_reduce_half` 日均 fills 從 ~500/24h 降到個位數
- COST EDGE 觸發頻率下降，觸發時 pnl_pct 分佈進入 [0.3%, 0.55%] 鎖利窄帶
- 同 symbol 同日最大半倉次數 ≤ 2

### P0-10 SCANNER-GATE — orphan_handler death loop fix（2026-04-17）

**問題**：策略在 scanner 輪替出的 symbol 上反復開倉 → orphan_handler A4 強平 → 策略再開 → 無限死循環。BASEDUSDT 為首例但影響 20+ symbols（228 筆 `ipc_close_symbol` fills）。

**修復（三部分）**：
1. **SCANNER-GATE**：`tick_pipeline` 新增 `symbol_registry` + Open dispatch 前 `is_active()` 檢查
2. **FUP-RACE**：`paper_state.proactive_mirror_insert()` — exchange 下單後立即寫 mirror 彌合 REST→WS 空窗
3. **A4 移除**：orphan_handler Stage A4 邏輯刪除，orphan 定義改為純「重啟後遺留」

**改動**：`tick_pipeline/mod.rs` · `on_tick.rs` · `paper_state.rs` · `orphan_handler.rs` · `event_consumer/mod.rs`
**測試**：engine lib 1351 / core 380 / orphan_handler 17/17 全綠

### P0-9 STABILITY-1 — 2026-04-16 停電事件 RCA（非代碼 bug，21d 時鐘不重置）

**背景**：同日更早 audit 在 watchdog.log 發現 9h 內 5 次 engine crash（後深撈實為 **30 次**），誤判為「代碼穩定性 P0-CRITICAL 阻塞」並要求重置 P0-2 LG-1 21d demo 時鐘。Operator 在回顧中提出假設：**「2026-04-16 10:00-16:00 local 停電 ~6h 造成斷網」**，要求驗證。

**RCA 證據鏈**（operator hypothesis 得證）：
- **時區**：operator 筆電 CEST (UTC+2)，UTC→local 加 2h
- **第一次 crash 10:45 local（08:45 UTC）** = 停電開始 45min 後（電池 + 路由器失電延遲）
- **watchdog 完全靜默 13:16-18:03 local（11:16-16:03 UTC，4h 47min blackout）** = 筆電電池耗盡或硬關機
- **post-gap 首條 `snapshot age=17313.5s`（4.81h 陳舊）** = 硬斷電復電鐵證
- **engine log（engine-1776330656.log，09:10 UTC 啟動）** 所有錯誤簽名一致：
  - `HTTP transport error: error sending request for url (https://api-demo.bybit.com/...)`
  - `IO error: failed to lookup address information: Temporary failure in name resolution`（DNS 失敗）
  - REST / WS private (`stream-demo.bybit.com/v5/private`) / WS public (`stream.bybit.com/v5/public/linear`) 全部連不上
- **零 panic / 零 assertion / 零 rust backtrace** — 純屬網路層斷線時的 fail-closed 合理行為
- 斷網恢復後（18:03 local 之後）網路仍不穩又滾了幾輪 crash，當前 PID 1364222 於 22:16 local 穩定啟動

**判定**：
- 30 次 crash = **單次基礎設施事件**（斷電斷網），非引擎代碼 bug
- **P0-2 LG-1 21d demo 時鐘不重置**：基礎設施事件 ≠ 引擎不穩定，否則每次停電都重置永遠達不到 504h
- **P0-3 Phase 5 edge 2w 重評**：crash 時段（10:45-18:03 local）fills 樣本自然為 0（引擎連不上 Bybit），不需特別排除
- **最早 Live 日期**：從樂觀估 W25 末（~2026-05-30）回到 **W24 末（~2026-05-23）**

**Nice-to-have（不阻塞，不急）**：
- `engine_watchdog` 可加 network-loss detection：連續 N 次 DNS failure 分類為 `network_outage`，不計入 stability strike
- 未來遇到類似事件自動區分基礎設施 vs 引擎 regression

**文件更新**：
- `TODO.md §P0-9` — 從 🔴 NEW P0-CRITICAL 改為 ✅ RCA 完成
- `CLAUDE.md §三` — STABILITY-1 條目重寫為 RCA 結論
- `CLAUDE.md §十` — 關鍵路徑劃掉 P0-9，Live 日期回到 W24 末
- `CLAUDE.md §十一` — 一句話狀態加入 RCA 結論，移除「日均崩潰 ≥5 次」誤述

**方法論教訓**：audit 發現的 crash 風暴在沒有 RCA 前不要輕易判定為 code-instability blocker；watchdog 記錄 + engine log 簽名（panic vs transport error）可快速鑑別 infra vs code root cause。

---

### LIVE-GUARD-1 — Rust 端 Mainnet 三重硬鎖回補（2026-04-16 深夜）

**背景**：SEC-17（2026-04-10 commit 25b5d73）在 GUI API key live_demo slot 功能推動下移除了 `OPENCLAW_ALLOW_MAINNET=1` Rust 端 env guard，意圖把門控外移 Python（`live_reserved` mode + Operator role auth）。但 2026-04-16 audit 揭露該遷移未補替代 fail-safe：`bybit_rest_client.rs:394` 僅 `tracing::warn!` 不擋、憑證空只 `warn!` + 後續 401、憑證 chain `param → BYBIT_API_KEY env → slot file` 讓任何能設環境變數的進程繞過 secret slot。Rust 長跑 × Python 重啟脆弱的對稱性崩潰。CLAUDE.md §三 / §四 標為 P0-CRITICAL 阻塞真實 live 上線。

**修復**（三重 Gate 加固，純 env 方案 — CLAUDE.md 建議選項之一）：
- **Gate #1**：恢復 `OPENCLAW_ALLOW_MAINNET=1` env 檢查（exact "1"，拒絕 "0"/"true"/"yes"/"1 "/" 1"），缺即 `BybitApiError::Business`
- **Gate #2**：`env=Mainnet` 時禁用 `BYBIT_API_KEY` / `BYBIT_API_SECRET` env var fallback，只允許 param → slot file（封閉 env 繞 slot 的攻擊面）。Demo/Testnet/LiveDemo 不受影響
- **Gate #3**：`env=Mainnet` 時憑證空 → 構造時 `Err` fail-closed（不再 warn! + 簽名階段 401 污染重試循環）
- `bybit_rest_client.rs:386-497` new() 重寫 + bilingual docstring

**測試**（+7，engine lib 1335→1342 / 0 fail；E2 對抗性審查 5/5 APPROVED）：
- `test_mainnet_blocked_without_allow_env` — 未設 env → Err（Gate #1）
- `test_mainnet_blocked_with_wrong_allow_value` — "0"/"true"/"yes"/"1 "/" 1" 全拒絕
- `test_mainnet_blocked_without_credentials` — allow=1 無 creds → Err（Gate #3）
- `test_mainnet_ignores_env_var_credentials` — `BYBIT_API_KEY` env 有值、slot 無 → 仍 Err（Gate #2 核心）
- `test_mainnet_accepts_explicit_param_creds` — allow=1 + param → OK（happy path）
- `test_demo_env_var_creds_still_work` — 回歸守衛：Demo + env var 不壞
- `test_testnet_no_guard_check` — 回歸守衛：Testnet 不需 allow env
- env-sensitive 測試用 `static LIVE_GUARD_ENV_LOCK: Mutex<()>` 串行化 + `EnvSnapshot` RAII 還原

**E2 對抗性審查**（5/5 APPROVED，Explore sub-agent）：
1. BybitRestClient 結構字面量繞過 — ✅ 無缺口（12 個 struct literal 全在 `#[cfg(test)]`，非測試代碼零 literal）
2. 調用方 Err 處理 — ✅ `startup.rs:432` return None 拒絕啟動、`openclaw_pyo3/client.rs:93` PyErr 傳回 Python 硬性失敗
3. 其他 HTTP client 打 mainnet endpoint — ✅ 無獨立 client，MarketDataClient 基於 BybitRestClient
4. WebSocket 獨立路徑 — ✅ BybitPrivateWs 接受預解析憑證無獨立讀取，public WS 無 Mainnet guard 需求
5. 環境變量語意誤用 — ✅ repo grep 0 結果，無既存 `OPENCLAW_ALLOW_MAINNET` 設值會被語意變更破壞

**架構影響**：真實 live 門控從 1 項 Rust-verifiable（secret slot 存在）升為 **3 項 Rust-verifiable**（Gate #1 env + Gate #2 cred source 限定 + Gate #3 fail-closed 構造）+ **2 項 Python-side**（live_reserved mode + Operator auth）= 共 5 項。任何單項失敗即拒絕構造 mainnet client。

**部署**：下次 `restart_all.sh --rebuild` 附帶生效。當前 LiveDemo → Demo endpoint 零影響；真實 Mainnet 僅在 operator 顯式配置 `trading_mode=Live` + `OPENCLAW_ALLOW_MAINNET=1` + secret slot 憑證三項俱全時可用。

**Commit**：<pending>

---

### P0-0 RECONCILER-BURST-FIX — Startup Grace Window 抑制對帳器啟動期誤升級（2026-04-16）

**背景**：2026-04-15 demo 引擎重啟後 46 分鐘卡在 Reduced 風控狀態無法開新倉。RCA 揭露 reconciler 首輪對帳 baseline 與本地 paper_state 未同步 → 殘留 Bybit 持倉被誤判為 live drift burst（6 Ghost + 2 Orphan）→ `BURST_DRIFT_COUNT=5` 門檻觸發 Defensive 升級 → FAST_TRACK `ReduceToHalf` 全組合半倉 + `ft_pause_new_entries` 鎖新開倉。阻塞 P0-1 G-2 驗證與 P0-3 Phase 5 edge 重評關鍵路徑。

**修復**（方案 A startup grace window 5min）：
- `escalation.rs`：新增 `STARTUP_GRACE_MS = 5 * 60 * 1000` 常量 + `ReconcilerState.startup_ms: u64` 欄位（預設 0 保留向後兼容）
- `evaluate_actions()` 入口：寬限期內早退返空 actions，**不累加** drift_streak / burst_drift_streak / clean_cycles，避免計數累積在寬限結束瞬間集中觸發
- `check_rest_failure_escalation()` 入口同樣 grace 檢查
- `run_position_reconciler()` 啟動時 `rc_state.startup_ms = now_ms_util()`
- 寬限期內 orphan_handler / V014 audit / baseline update 全部照常運作（只抑制升級決策分發）

**測試**（+6，engine lib escalation::tests 13→19）：
- `test_startup_grace_suppresses_burst_escalation` — 寬限期內 5-drift burst 不升級、計數器不累加
- `test_startup_grace_suppresses_persistent_drift` — 寬限期內 3 cycles 持續 drift 不累加 streak
- `test_startup_grace_suppresses_single_drift` — 寬限期內單 drift 不升 Cautious
- `test_after_grace_burst_escalates_normally` — 寬限期過後首個 burst 正常升 Defensive（streak=1）
- `test_startup_grace_suppresses_rest_failures` — 寬限期內 REST failure tier3 不升級
- `test_startup_ms_zero_preserves_legacy_behaviour` — 舊調用方（startup_ms=0）保留 P0-0 前行為
- `test_startup_grace_boundary_exclusive` — `now - startup == STARTUP_GRACE_MS` 邊界已離開寬限期
- 全回歸：engine lib 1330 default + 18 reconciler_e2e + 35 stress_integration passed / 0 fail

**RCA 文件**：`docs/references/2026-04-16--reconciler_burst_escalation_rca.md`（症狀/根因/三方案比較/實作清單/驗收）

**解鎖**：P0-1 G-2 FundingArb 驗證（部署後 daemon 重新計時）+ P0-3 Phase 5 edge 2w 重評（乾淨窗口累積）

**Operator 部署驗收**：`restart_all.sh --rebuild` → 前 5min 觀察 `startup grace` suppression 日誌 → 前 5min governance 保持 NORMAL → 乾淨環境 30min 內 NORMAL 穩定

### EDGE-P3-1 ML-MIT #26 — Stage 2 Quantile LGBM + CQR + Per-strategy ONNX Export（2026-04-15 · commit `cdac922`）

**目標**：Lane A 純 Python 訓練管線，與 FA-PHANTOM-2 Rust 修復並行安全（零檔案重疊）；交付 Phase B #3 ONNX loader + CC T2/T7/T18 所需的首個 per-strategy ONNX artifact 能力。

**交付**（5 檔改、10 檔加，2645 insertions）：
- `quantile_trainer.py`（新，~540 行）— q10/q50/q90 三獨立 pinball LGBM + CPCV purge + 策略特定 embargo（funding_arb 3-fold/72h/14d vs 其他 5-fold/24h/7d）+ 指數樣本權重 `w = exp(-days_ago/14)` + tail holdout split（總跨度 < holdout 窗時退回 min_fraction 比例切分）+ linear-QR floor baseline + 1000-bootstrap decile-lift 95% CI + 分位交叉率 + `feature_schema_hash = sha256(version || "|" || names.join("\n"))` 與 Rust FeatureVectorV1 契約一致
- `calibration.py`（擴展）— CQR 單邊 marginal 校準 Romano 2019 + `(n+1)` 有限樣本修正 `q_level = ⌈α·(n+1)⌉/n`：`fit_cqr_offset` / `fit_cqr_trio` / `apply_cqr_to_quantile` / `evaluate_cqr_coverage` / `fit_isotonic_fallback`；舊 isotonic 路徑保留不動
- `onnx_exporter.py`（擴展）— `export_quantile_trio_to_onnx()` 三檔匯出 + POSIX-atomic symlink swap（`tmp.symlink_to → os.replace`）+ per-file 精度 gate `max|LGB-ONNX| < 1e-3` on 1000 random vectors；檔名規範 `edge_predictor_{engine}_{strategy}_{quantile}_{schema}_{date}.onnx` + `_current` symlink 匹配 Rust loader 契約（spec §7.2）
- `quantile_reports.py`（新，~345 行）— 5 硬性 gate（pinball skill > 0.10 / coverage error < 3pp / decile lift CI lower > 1.3 + point ≥ 1.5 / crossing < 1% / LGBM vs linear-QR skill diff ≥ +5pp）+ 樣本量桶（<200 / 200-499 / ≥500）→ should_ship / shadow_only / no_ship 裁決 + 1000 random vector train-serve skew harness；JSON 持久化
- `run_training_pipeline.py`（重構）— `use_quantile_predictor=True` 分支路由 ETL → quantile_train → CQR → acceptance_report → per-quantile ONNX（verdict ≠ no_ship 才匯出）；legacy regression scorer 路徑零行為改變

**測試**（+47，ml_training 135→182 passed）：
- `test_quantile_trainer.py` — 23 tests（embargo 路由 funding_arb / default / 大小寫、權重衰減、pinball/coverage/crossing/decile lift、schema hash 穩定性 + version 差分、tail holdout 邊界 fallback、端到端 lgb-guarded）
- `test_calibration_cqr.py` — 9 tests（CQR 有限樣本公式手動驗證、α 單調、coverage gap 5pp 內收斂、isotonic fallback 單調性）
- `test_quantile_reports.py` — 11 tests（verdict 4 路由、gate 邊界 strict `>`、post-CQR coverage source、linear-QR unavailable 視為 pass、training failure 短路）
- `test_onnx_exporter_quantile.py` — 4 tests（engine_mode / quantile 輸入驗證、end-to-end 精度、symlink swap idempotency）
- 218 passed / 10 skipped（重依賴 lgb/onnxmltools/onnxruntime/sklearn 缺失時 `pytest.importorskip`）/ 0 regression

**解鎖**：Phase B #3 ONNX loader（Rust 側等首個 artifact）· CC T2/T7/T18（train-serve skew + precision）· Stage 3 Shadow mode（#29）

**Handover**：`docs/worklogs/2026-04-15--lane_a_ml_mit_26_trainer_handover.md`（pre-compact 14-section brief，記錄所有設計決策）

### FA-PHANTOM-2 — fast_track held-symbol scoping + sigma gate（2026-04-15）

**發現過程**：G-2 FundingArb 監控 daemon PID 598572 運行 7 小時，progress 停在 0/20 fills。DB 查詢揭露 demo funding_arb 8 次開倉全部在 4-7 秒內被 `risk_close:fast_track` / `risk_check` / `ipc_close_symbol` 秒殺，0 次走到自然 `strategy_close` 出口。engine.log 抓到 `risk_level=Normal` 下 `FAST_TRACK CloseAll fired` 多次，`trigger_symbol=ENJUSDT`（小幣 $0.075 ~ $0.094）。排除 CircuitBreaker / margin_util (已 leverage-aware ≤2%) 後確認唯一觸發源是 `price_drop_pct >= 5.0`。

**根因**：`openclaw_core/src/risk/price_tracker.rs::max_drop_pct()` 掃全部 25+ 觀察幣種 5min 窗口最壞跌幅。小幣 5min 內抖 5% 是常態噪音，所以 fast_track 持續誤觸 CloseAll，**全策略被系統性秒殺**，funding_arb 在 daemon 視角下永遠收不滿 20 個自然出口 fill。與 FA-PHANTOM-1 同類型 bug（fast_track false-positive CloseAll），但根因獨立。

**交付**（3 處協調修改）：
- **`PriceHistoryTracker::worst_drop_for_held(&[String]) -> Option<SymbolDropInfo>`** — 新方法僅掃持倉幣種，附帶 sigma = `|current - mean| / std_dev`（窗口內）。空集合或樣本不足返回 None。舊 `max_drop_pct()` 保留供非 fast_track consumer 使用。
- **`evaluate_fast_track` 新簽名** `(risk_level, held_drop_pct, held_drop_sigma, margin_util)`，分級規則：
  - `CircuitBreaker+` / `margin_util >= 90%` → CloseAll（舊行為，保留）
  - `held_drop_pct >= 15%` → CloseAll（真閃崩兜底，sigma 可能不可用的邊緣情境）
  - `held_drop_pct >= 5% AND sigma >= 3` AND `risk >= Defensive` → CloseAll
  - `held_drop_pct >= 5% AND sigma >= 3` AND `risk < Defensive` → ReduceToHalf（關鍵：Normal 下不再 panic，只半倉）
  - 其他按舊風控梯度（Defensive→ReduceToHalf, Reduced→PauseNewEntries）
- **`tick_pipeline/on_tick.rs`** — 構造 `held_symbols` 清單 → `worst_drop_for_held` → 解包 `(drop_pct, sigma, symbol)` → 傳入 `evaluate_fast_track`。三個 tracing 日誌（CloseAll WARN / ReduceToHalf WARN / PauseNewEntries INFO）全部攜帶新欄位 `held_drop_pct`/`held_drop_sigma`/`held_drop_symbol` 便於日後取證。

**測試** (+17 淨增)：
- `price_tracker::tests` +8 — 空 held 返 None · unheld symbol drop 不觸發（legacy 仍會，分岔驗證）· held drop 正確浮現 · 樣本不足返 None · 多 held 取最大 · 穩定幣 0 跌返 None · 噪音小幣 sigma<3 · 穩定幣突崩 sigma≥3（19 穩定樣本避免 std_dev 被 outlier 自身撐高到 sigma=3.0 邊界）
- `fast_track::tests` +9 — 新簽名全部 arity 更新；新增 FA-PHANTOM-2 regression（6%+sigma=1.5 → NoAction）+ held outlier Normal/Cautious → ReduceToHalf + Defensive → CloseAll + 5%/3σ 邊界 + 15% cliff + 無 drop 訊號 risk-level-only 退化
- `stress_integration` 語義更新 — 舊 `test_flash_crash_closes_all`（8% Normal → CloseAll）改為測新語義的三條路徑，`boundary_exactly_5pct_drop` 重命名為 `boundary_extreme_drop_cliff` 驗 15% 硬線

**計量**：engine lib 1309→1318（+9）；core 372→380（+8）；e2e 35 不變。合計 **Rust 1716 → 1733 passed / 0 failed**。

**Spec 與決策記錄**：`docs/references/2026-04-15--fa_phantom_2_fix_spec.md`（含根因證據鏈、三條修復方向對應表、閾值選擇理由、測試列表、FA-PHANTOM-1 對照）。

**部署**：`restart_all.sh --rebuild` 重建 engine binary；驗證指標為 `grep "FAST_TRACK CloseAll fired.*risk_level=Normal" /tmp/openclaw/engine.log` 應回空（除非真發生 ≥15% 或 5%+3σ 事件），G-2 daemon 接下來幾小時應開始累積 `n_fills`。

---

### EDGE-P3-1 Phase B #4 — RNG seeding + `with_kind` forwards kind to IntentProcessor（2026-04-15）

**背景**：spec §7.3 F9 規定 paper/demo/live 各自以 `seed_for_engine(startup_nanos, kind) = startup_nanos ^ kind_discriminant` 初始化 ε-greedy 的 `SmallRng`。函式本身在 `edge_predictor/gate.rs` 早已實作 + 有單元測試，但 bootstrap 從未呼叫 — `IntentProcessor::new()` 預設 seed=0，三引擎的 ε-greedy 抽樣流完全相同（spec §7.3 F9 失效）。同時發現一個耦合的潛伏 bug：`TickPipeline::with_kind(kind)` 把 kind 寫到 `pipeline.pipeline_kind` 卻從未 forward 給 `pipeline.intent_processor.pipeline_kind` — gate 用的是 IntentProcessor 這份欄位，導致 demo/live 的 gate 全部誤認為 Paper，ε-greedy 在 demo/live 也會嘗試發 `EmitShadowFill`，靠 writer R5 + DB `CHECK (engine_mode='paper')` 才擋下。兩者都屬「設計已就位，bootstrap 缺一個 setter 呼叫」。

**交付**：
- **`TickPipeline::set_predictor_rng_seed(seed: u64)`**（`tick_pipeline/mod.rs`）：純 forwarding wrapper → `intent_processor.set_predictor_rng_seed`。與 `set_shadow_fill_tx` / `set_decision_feature_tx` 同一設計。
- **`TickPipeline::with_kind(kind)`** 加一行 `p.intent_processor.set_pipeline_kind(kind)` — gate 的 `inputs.engine_kind` 這下才真正反映 engine；註解說明為何單一 setter call 同時修復兩個面向（persistence + gate）。
- **`event_consumer/mod.rs`** bootstrap wire（與 7a/7c/store 注入同區塊）：`SystemTime::now()` nanos → `gate::seed_for_engine(nanos, pipeline_kind)` → `pipeline.set_predictor_rng_seed(seed)`。`unwrap_or(0)` 防止 1970 年代容器時鐘異常時 panic（kind discriminant XOR 仍使三引擎得到互異種子）。
- **`IntentProcessor::pipeline_kind()`** 讀取 accessor（pub）+ `predictor_rng_lock_for_tests`（`#[cfg(test)]`）：讓回歸測試可驗證 with_kind forwarding 與 seed 獨立性，不把 private state 洩漏到 non-test API。

**測試** (+2 於 `tick_pipeline::tests`)：
- `test_with_kind_forwards_kind_to_intent_processor` — 三個 `with_kind` 的 pipeline 的 `intent_processor.pipeline_kind()` 必須分別為 Paper/Demo/Live；鎖定 forwarding 不會被未來重構靜默回歸。
- `test_set_predictor_rng_seed_changes_draw_stream` — 兩 pipeline 分別以 `seed_for_engine(123_456_789, Paper)` 和 `seed_for_engine(123_456_789, Demo)` reseed，各抽 64 bit，向量必不相等 — 證明 RNG wiring 實際改變了 Mutex 內的 SmallRng 狀態。

**計量**：lib 1307→1309（+2）；core 372 不變；e2e 35 不變。合計 **Rust 1716 passed / 0 failed**。

**下一步解鎖**：Phase B 剩 #3（ONNX model loader，blocked by ML-MIT #26）。#4 完成後 spec §7.3 F9 完全符合，paper 的 exploration 每次冷啟動後種子隨 wallclock 而異（好的 diversity），demo/live 的 ε-greedy 則被 gate 層直接擋住（不再依賴 writer/DB 兜底）。

### EDGE-P3-1 Step 7b — `ReloadEdgePredictor` plumbing-only（2026-04-15）

**背景**：spec §7.3 Step 7 最後一條 IPC。Python ML-MIT pipeline 將來會把新訓練的 ONNX artifact 寫到磁碟後呼叫此 IPC 讓 Rust 熱換；但 ONNX loader 本體仍卡在 ML-MIT #26（tract/ort feature flag 空殼）。直接等 #26 會讓 IPC 協定長期懸空；直接全做又需要未完成的載入器。**決策**：落 plumbing-only — 協定/handler/validation/tests 全就位，loader 為存根（恆 Err 帶 `awaiting ML-MIT #26` 字樣），capability flag 誠實保持 `False`。#26 交付時換 loader body + 翻 flag + 加 Python route 即可，無協定改動。

**交付**：
- **`PipelineCommand::ReloadEdgePredictor`** variant（`tick_pipeline/mod.rs`）：`engine: String`（白名單 paper/demo/live，作 IPC 路由二次防禦）+ `strategy: String` + `path: PathBuf` + `response_tx: oneshot::Sender<Result<String, String>>`。注釋標記 plumbing-only 與 flag 翻轉時機。
- **`edge_predictor::load_predictor_from_path`** 存根（`edge_predictor/mod.rs`）：`path.exists()` false → 立即 Err（讓路徑錯誤仍可測），存在則 Err `onnx_loader_not_wired: awaiting ML-MIT #26 first ONNX artifact`。注釋指明 #26 交付時的替換步驟。
- **`handle_reload_edge_predictor`**（`event_consumer/handlers.rs`）：engine `.trim()` + 白名單 match（防 Python proxy 殘留換行）→ `pipeline.edge_predictor_store()` 存在性檢查（`None` 直接 Err 避免 loader 成功卻熱換進空引用）→ 呼叫 stub loader → 成功才 `store.swap(strategy, predictor)` + info log。拆為獨立函式以便單元測試免 oneshot 迴圈即可驗。
- **Match arm** 於 `handle_paper_command` 加入 `PipelineCommand::ReloadEdgePredictor => handle_reload + oneshot 回應`。
- **Capability flag 註解** `engine_capabilities_routes._EDGE_P3_IPC_SUPPORT.reload_edge_predictor`：值仍 `False`，註解改為「protocol wired; stays False until ML-MIT #26 replaces the stub loader with real tract/ort backend」。
- **Python route 暫不加**：flag `False` 時無 client 會呼叫；避免寫完整路由卻只能代理 Err。#26 交付時 Python route + flag flip + 實作 loader 同一 PR 落地更清晰。

**測試** (+4 於 `event_consumer::handlers::tests`)：
- `test_reload_edge_predictor_rejects_unknown_engine` — `engine="mainnet"` → Err 含 `invalid engine`。
- `test_reload_edge_predictor_requires_store` — 未 `set_edge_predictor_store` → Err 含 `EdgePredictorStore not wired`。
- `test_reload_edge_predictor_stub_loader_errs` — 接線 store + `NamedTempFile` 確保路徑存在 → 走完整 loader → Err 含 `onnx_loader_not_wired` + `ML-MIT #26`；`store.loaded_count() == 0` 確認未熱換。
- `test_reload_edge_predictor_trims_engine_name` — `engine="  paper\n"` → 白名單仍通過（trim 生效）→ err 走到 loader 路徑而非 invalid engine。

**計量**：lib 1303→1307（+4），其餘集合不變。zero churn on Step 7a/7c/7d/7e/7f 路徑。

**下一步解鎖**：Step 7 IPC 全套協定/實作就位。Stage 2+ 唯一剩下的阻塞仍是 ML-MIT #26 首 ONNX artifact — 屆時 stub loader body 換真、capability flag 翻 True、Python route 加（`POST /api/v1/risk/edge_predictor/reload`，沿用 `ReloadRiskConfig` 的 operator 授權）即完整端到端。

### EDGE-P3-1 Step 7c — `EmitShadowFill` → `learning.decision_shadow_fills` writer（2026-04-15）

**背景**：spec §7.3 Step 7 的 ε-greedy paper exploration 持久化 — 預測器對成本拒絕但探索翻硬幣通過，此時合成「shadow fill」僅供觀測學習，**永不**納入訓練 label 回填（`parquet_etl.py` §5.1 WHERE 以 `close_tag='shadow_fill:epsilon_greedy'` 排除）、永不進 live/demo 真實交易。目前僅 Stage-0 stub handler（log-only），本 step 填完 Rust-direct writer，對稱 Step 7a `DecisionFeatureSnapshot` 的 Option-B（IntentProcessor producer + IPC passthrough 共用同一 writer channel）。

**交付**：
- **Rust writer**（`database/shadow_fill_writer.rs` 新 ~230 行）：`run_shadow_fill_writer` async mpsc drain；`HashMap<context_id, ShadowFillMsg>` flush 前去重（ε-greedy 每 intent 至多一次，但 replay/passthrough 可重發同 id）；`batch_flush_interval_ms` 定時 flush；`flush_shadow_fills` 三道拒絕：DB-RUN-6 `ts_ms=0` epoch 洩漏 + R5 `engine_mode != "paper"` 第二道防線（gate 已保證 is_paper，writer 亦拒避 PG CHECK 失敗計入 pool 失敗閾值）+ malformed JSONB warn+skip；INSERT 11 欄位（context_id/ts/engine_mode/strategy_name/symbol/side/features_jsonb/predicted_q10/predicted_q50/predicted_q90/cost_bps_at_open），`synthetic_*` + `close_tag` **刻意** 不 bind 走 V017 DDL 預設（DDL 漂移時 writer 保持向下相容）。
- **ShadowFillMsg**（`database/mod.rs`）：carrier struct 11 欄 + `#[derive(Debug)]`。
- **side 欄位接線**：`PipelineCommand::EmitShadowFill` variant 加 `side: i8`，`ShadowFillPayload` 加 `pub side: i8`，`edge_predictor_gate` 建構時從 `features.side` 取值（`FeatureVectorV1` 既有欄位），`emit_shadow_fill` 透傳；DB 表既有 `side SMALLINT NOT NULL`，不透傳會 bind 階段報錯。
- **TickPipeline 接線**（`tick_pipeline/mod.rs`）：`shadow_fill_db_tx: Option<Sender<ShadowFillMsg>>` 欄位 + `set_shadow_fill_db_tx`（`debug_assert!` 防雙注入）+ `shadow_fill_db_tx()` getter。
- **Handler 轉實作**（`event_consumer/handlers.rs`）：`EmitShadowFill` 從 Stage-0 log-only stub 轉為 `try_send` off hot path，Full/Closed 丟棄+warn，engine_mode 由 `pipeline.pipeline_kind.db_mode()` 推導（gate 僅 paper 發，但仍計算交 writer R5 防線驗證）；`None` tx 走 fail-soft log 分支。
- **spawn_db_writers** 5→6 tuple（`tasks.rs`）：capacity 1024，對齊 decision_feature。
- **3 `EventConsumerDeps` sites** (`main.rs` paper/demo/live)：paper 為唯一合法 emission 來源（gate guard），demo/live 亦接線作深度防禦日誌（異常洩漏可見於 writer warn log 而非污染 PG）。
- **event_consumer wire**（`mod.rs`）：destructure deps + `set_shadow_fill_db_tx` 注入（對稱 `decision_feature_tx` 模式）。
- **Python capability flag**：`engine_capabilities_routes._EDGE_P3_IPC_SUPPORT.emit_shadow_fill: False → True`。

**測試** (+7)：`test_dedup_keeps_latest`、`test_dbrun6_epoch_zero_detected`、`test_non_paper_engine_mode_rejected_in_carrier`、`test_malformed_jsonb_caught_before_sql`、`test_valid_jsonb_parses`、`test_side_fits_smallint`、`test_insert_sql_locked_columns`（`split_once("INSERT INTO") → split_once("VALUES")` 範圍鎖定，避開註解/docstring 誤報；驗 9 欄位齊全 + `close_tag` 不顯式 bind）。lib 1296→1303，engine-capabilities 6 tests 繼續通過，e2e 35 ok。

**Stage 2+ blocker 狀態**：Step 7 IPC 已完成 5/6（7a/7c/7d/7e/7f）；餘 7b `ReloadEdgePredictor` 可獨立前推，其餘唯一 blocker 仍為 ML-MIT #26 首 ONNX artifact。

### EDGE-P3-1 Step 7f — `GET /api/v1/engine/capabilities` 探針端點（2026-04-15）

**背景**：EDGE-P3-1 §12.3 item 7 的 backward-compat capabilities probe。spec 僅標 `(backward-compat)` 無詳細 schema — 解讀為「端點存在 + 預期 shape 即表示此 build 支援 EDGE-P3-1，舊 build 回 404 讓 client 優雅降級」。刻意保持薄，不重複 `/api/v1/paper/risk/config/engine/{engine}` 的完整 RiskConfig 快照。

**交付**（`program_code/exchange_connectors/bybit_connector/control_api_v1/app/engine_capabilities_routes.py` 新檔 ~180 行 + `main.py` +4 行註冊 + `tests/test_engine_capabilities_routes.py` 新檔 ~180 行）：
- **路由** `/api/v1/engine` prefix，`GET /capabilities`，`Depends(base.current_actor)`（viewer 即可，純讀取探針）。回傳三段：
  - `feature_schema` — `FEATURE_NAMES_V1` 鏡像（`schema_version="v1"`、`dim=17`、`names`）從 `program_code/ml_training/parquet_etl.EDGE_P3_FEATURE_NAMES` 匯入，複用既有 DO-NOT-REORDER 契約避免新增鏡像副本。
  - `ipc_methods` — 本 build 宣告哪些 Step 7 IPC 變體已接線的 bool 字典：`decision_feature_snapshot=True`（7a）· `fsynced_toml_write=True`（7d）· `disable_edge_predictor_all=True`（7e）· `reload_edge_predictor=False`（7b pending）· `emit_shadow_fill=False`（7c pending）· `set_edge_predictor_shadow=False`（v1.3 U1 pending）。唯一防漂移宣告 — 後續 PR 接線時必須同步翻旗。
  - `engines` — per-engine (paper/demo/live) 窄 edge_predictor 視圖（`use_edge_predictor`、`shadow_mode`、`quantile_safety_k`、`require_q10_positive_for_adds`、`exploration_rate`、`fallback_on_error`），經 `get_risk_config` IPC 逐引擎取。
- **Fail-closed 契約**：IPC 不可用（測試、cold boot、engine 崩）仍回 HTTP 200 + `degraded=true` + `reason` 字串（`ipc_unavailable` / `ipc_error:{ExcClass}` / `bad_payload_shape`），靜態部分（feature_schema / ipc_methods）永遠可用。絕不 5xx。模組級 `_IPC_CLIENT` 懶初始化單例（複用 `risk_routes._get_direct_ipc` 樣式）。
- **Envelope** 符合既有慣例：`{"ok": true, "data": {...}, "is_simulated": false, "data_category": "engine_capabilities"}`。
- **6 新 tests**（`test_engine_capabilities_routes.py`）：
  - `test_capabilities_returns_200_without_ipc` — 無 IPC 仍回 200。
  - `test_capabilities_degraded_when_ipc_down` — `degraded=true` + `reason="ipc_unavailable"` + 所有 engines 欄位 None。
  - `test_capabilities_static_payload_present_when_degraded` — schema.names 17 + adx_1h/is_funding_settlement_window 端點 + ipc_methods 完整。
  - `test_capabilities_happy_path_surfaces_engines` — 存根 IPC 回三引擎差異化值（paper use=true/demo=false/live=false + exploration_rate 分流）→ route 正確路由。
  - `test_capabilities_envelope_shape` — ok/is_simulated/data_category + engines 三鍵完整。
  - `test_capabilities_requires_auth` — 無 `dependency_overrides` → 401（`current_actor` 拒絕空 token）。

**測試**：Python **2852→2875 pass / 0 fail / 5 skipped**（control_api_v1 子集 `2452 passed`，含新增 6）。Rust 測試未觸（Step 7f Python-only）。

**為何未新增 Rust IPC**：刻意避免 scope creep。`get_risk_config` IPC（ARCH-RC1 1C-2-C / LIVE-P2-1）已是三引擎完整 RiskConfig 讀取管道；Step 7f 只需薄 wrapper 抽 edge_predictor 窄子集 + 疊靜態宣告。未來若 `ipc_methods` 宣告維護壓力變大，可升級為新 Rust `get_engine_capabilities` IPC 由引擎自報（source of truth 移至 Rust），但 Step 7f 完工時機械漂移風險低（`_EDGE_P3_IPC_SUPPORT` 常數字典每條都註記 commit 號 + spec 條款）。

**下一步**：Step 7 餘 2 條（7b `ReloadEdgePredictor{engine, strategy, path}` IPC + Python route · 7c `EmitShadowFill` Python consumer → `learning.decision_shadow_fills`）。兩條獨立可推。

---

### ORPHAN-ADOPT-1 Phase 2A — 確定性 Adopt 基礎設施（2026-04-15）

**背景**：Phase 1（2026-04-14 merged）+ FUP 側車 mirror 解決了「偵測到但不動」與「引擎自殺」的 bug，但所有真正的外來 orphan 都走 Stage C `SoftConservative` close-everything 降級路徑。Phase 2 原本等 G-1 R-02 AI Strategist（W22-W23）。Phase 2A 是非 agentic sub-option：用既有 `edge_estimates` 表當「某策略會下這個幣種」的確定性代理 — 任一 `KNOWN_STRATEGY` 在 orphan 幣種 shrunk_bps > 0 即 Adopt。edge 正負僅是 per-symbol 指標，方向（long/short）保留交易所回報的原樣，StopManager 管下行。

**交付**：
- **Schema** — `PaperPosition.owner_strategy: String` 必選欄位。strategy-driven fills 寫 `intent.strategy`；`import_positions` + `upsert_position_from_exchange` insert 路徑寫 `"bybit_sync"`；`adopt_orphan` 寫 `ORPHAN_ADOPTED_STRATEGY = "orphan_adopted"`；update 路徑保留既有 owner（ma_crossover 收到 WS 更新不會被改回 bybit_sync）。`apply_fill` 加第 7 個 positional 參數 `owner_strategy: &str`，同向累加 first-write-wins。`#[serde(default)]` 讓 pre-2A snapshot 文件可載入。
- **Stage B2 Adopt 決策** — 新 `OrphanStage::AdoptPositiveEdge` + `OrphanDecision::Adopt { reason, stage, triggering_strategy }`。`handle_orphan()` B1/B2 分支：任一 known strategy 在 `pos.symbol` 有 `shrunk_bps > 0` → Adopt，記下第一命中（per `KNOWN_STRATEGY_NAMES` 順序）為 `triggering_strategy`；否則 `unrealised_pnl > 0` → SoftLockProfit close；否則 Stage C 落入 SoftConservative close（原則 #6 保守優先）。Stage A（liq / CB / notional / scanner universe）嚴格先於 B，安全檢查永不讓步 Adopt。
- **注入路徑** — 新 `PaperState::adopt_orphan(symbol, is_long, qty, entry_price, ts_ms) -> bool`：冪等 · 輸入守衛 · 預填 `latest_prices`（StopManager 立即有 tick）· 用 `positions_insert` helper 寫入（FUP 側車 mirror 自動更新）· 寫 `owner_strategy = ORPHAN_ADOPTED_STRATEGY`。新 `PipelineCommand::AdoptOrphan` fire-and-forget + `event_consumer/handlers.rs` 分派 arm（插入後 force_write snapshot）。新 `dispatch_orphan_adopt(decision, pos, cmd_tx)`（用 `pos.avg_price` 作 adopt entry_price，StopManager 從此點管下行）；與 `dispatch_orphan_close` 都拒錯誤 variant（warn + `return false`）。`position_reconciler/mod.rs:635` 分派分叉依 decision variant。
- **Audit 擴展** — V014 JSONB payload 加 `owner_strategy`（Adopt=`"orphan_adopted"`/Close=null）+ `triggering_strategy`（Adopt=命中策略名/Close=null），下游分析可 join 歸因。
- **測試** — lib 1285→1293 (+8)：5 `orphan_handler.rs`（long Adopt/short Adopt/無正 edge 落 SoftConservative/first-positive-edge wins deterministic/Stage A 優先於 B2）+ 3 `paper_state.rs`（insert + mirror + idempotent 保留 owner + 輸入守衛）。

**測試總數**：lib **1285→1293**（+8）· core 372 · e2e 35 · **total 1692→1700 pass / 0 fail**。

**Deploy**：`bash helper_scripts/restart_all.sh --rebuild`。Adopt 路徑在 `edge_estimates.json` 未 populated OR 無 `KNOWN_STRATEGY` 在 orphan 幣種有正 edge 時仍然 inert（退回 Phase 1 close-only）。

**Phase 2B（未來）**：G-1 R-02 Strategist 在線後，Adopt 規則從「正 shrunk edge」升級為「Strategist would_take(symbol, side)」；`KNOWN_STRATEGY_NAMES` + `EdgeEstimates` probe 降為 fast-path short-circuit，Strategist 為 slow-path 最終裁定。

---

### EDGE-P3-1 Step 7e — `DisableEdgePredictorAll` 完整兩階段 commit + V014 audit（2026-04-15）

**背景**：commit `97777d5` 已落 Step 7e 骨架（介面 + getter + 標準入口函式，語義仍 pre-7e memory-only clear）。本 commit 填上完整兩階段邏輯 + V014 audit + 3 新測試，kill-switch 於 operator 下令後必須保證「即使引擎立刻崩潰，重啟仍讀到 `use_edge_predictor=false`」—disk-first fail-abort 語義。

**交付**（`event_consumer/handlers.rs` +180 / -40，不觸骨架範圍外檔）：
- **兩階段 commit 邏輯**（`disable_edge_predictor_all_impl`）：
  - Stage 1 — 預算 next `RiskConfig`（`edge_predictor.use_edge_predictor = false`）+ `validate()` → `write_toml_atomic_fsynced(&next, persist_path)` disk-first；寫盤失敗立即 reject 且不觸及記憶體，避免「disk 舊 + 記憶體新」的半啟用殘局。
  - Stage 2 — `ConfigStore::apply_patch(Operator, mutate, validate)` ArcSwap 把同一 mutation 套到 live config；Stage 2 失敗（只有 lock poison）時 disk 已是 authoritative 新副本，重啟自動對齊 + warn log 提示 operator。
  - Stage 3 — `EdgePredictorStore::clear_all()` 清記憶體 slot，返回清空計數。
  - Fallback — `risk_store` 未接線（測試或未來 stripped-down engine）降級為 memory-only clear，回 `cleared N slots (memory-only)` 讓 caller 區分兩路徑。
- **V014 audit**（fire-and-forget `tokio::spawn`，僅 `audit_pool.is_some()` 時 enqueue）：`event_type='predictor_disabled_all'` / `source='operator'` / `config_name='risk_config'`，payload JSONB `{operator_token_hash(sha256hex), reason, cleared_slots, persisted, engine_mode, stage2_error}`；raw token 永不落盤。`tokio::spawn` 需要 runtime → 測試傳 `audit_pool=None` 跳過 spawn，單元測試無需 tokio。
- **U1 authz**：`operator_token.len() < 32` 立即 reject（未來 HMAC 驗證 hook）；`hash_operator_token()` 用 `sha2::Sha256 + hex::encode` 產生審計專用 hash。
- **3 新測試**（`handlers.rs` tests 模組）：
  - `test_handle_disable_edge_predictor_all_rejects_short_token` — 9 字符 token → Err("too short")；slot 不觸動（reject 先於 `clear_all`）。
  - `test_handle_disable_edge_predictor_all_memory_only_when_store_unwired` — `set_risk_store()` 不呼叫 → risk_store=None → memory-only clear 路徑；訊息含 "memory-only"。
  - `test_handle_disable_edge_predictor_all_writes_toml_stage1` — 接線 `ConfigStore::new(RiskConfig { use_edge_predictor: true, ..default }).with_toml_persist(tempdir)` → call handler → 驗 TOML 檔內容含 `use_edge_predictor = false`、in-memory snapshot `use_edge_predictor == false`、pred_store slot 清空、回應訊息含 `persisted=false`。
- **`handle_paper_command` DisableEdgePredictorAll arm**：延用共用 `disable_edge_predictor_all_impl`，以 `db_mode="paper"` + `audit_pool=None` 呼叫，保留 legacy test path + 避免單元測試需要 tokio runtime。

**測試**：lib **1293→1296**（+3 Step 7e）· core 372 · e2e 35 · **total 1700→1703 pass / 0 fail**。

**為何兩階段非純 apply_patch**：spec §8.8 F3b 要求 disk-first — `apply_patch` 內建 `maybe_persist` 是 fail-soft（寫盤失敗只 warn，ArcSwap 仍 commit），對 kill-switch 語義不夠嚴格（operator 意圖是「再也不讓它啟用」，寫盤失敗後必須中止而非吞錯）。因此 Stage 1 用直接的 `write_toml_atomic_fsynced` + fail-abort，Stage 2 才走 `apply_patch`（此時 disk 已有 authoritative 副本，ArcSwap 失敗也有磁碟 fallback）。

**audit 設計**：token 永不落 raw。即便 Postgres 被入侵/洩漏，審計表只有 sha256 hash，無法 replay token；log 只寫 `token_len` + `reason` + `cleared_slots` + `engine_mode` 足以溯源 operator 意圖。

**已知限制**：跨三引擎（paper/demo/live）原子 disable 未實現 — 若 operator 要全局 kill，需 Python 側 fan-out 三次 IPC 呼叫；任一引擎失敗由 Python 決定補救/回滾。Rust 側只保證單引擎 3-stage 原子。

**下一步**：Step 7b `ReloadEdgePredictor{engine, strategy, path}` IPC + Python route · Step 7c `EmitShadowFill` Python consumer → `learning.decision_shadow_fills` · Step 7f `GET /api/v1/engine/capabilities`。三條獨立可推。

---

### EDGE-P3-1 Step 7e skeleton — `DisableEdgePredictorAll` 骨架（2026-04-15 · commit `97777d5`）

**背景**：Step 7d 交付 `write_toml_atomic_fsynced` 耐久性證明；本 commit 是 Step 7e 的**骨架**（非完整兩階段 commit + audit），為了讓 Phase 2A 能獨立以清潔 commit 落地，把 Step 7e 的 wire-up 拆出來先行。完整兩階段 commit + V014 audit row 仍 FIXME，留待下一 Step 7e commit 完成。

**骨架交付**（5 files +156 / -28）：
- **`tick_pipeline/mod.rs`**：`PipelineCommand::DisableEdgePredictorAll` 從 `{response_tx}` 擴為 `{operator_token, reason, response_tx}`；U1 授權 envelope（Python proxy 填 per-session UUID，Rust 側 `len>=32` 檢查，未來 HMAC 驗證 hook）；`reason` = operator 填 free-text 審計原因。新增 `TickPipeline::risk_store()` getter。docstring 展開 Stage 1 TOML fsync → Stage 2 ArcSwap → Stage 3 clear_all + V014 audit 語義。
- **`config/store.rs` + `config/mod.rs`**：`ConfigStore::persist_path() -> Option<&Path>` getter；`write_toml_atomic_fsynced` 從 `pub(crate)` 升 `pub` 並於 `config` 模組重新導出。
- **`event_consumer/handlers.rs`**：新 `pub fn handle_disable_edge_predictor_all(operator_token, reason, response_tx, pipeline, _db_mode, _audit_pool)` 標準入口 — **當前行為是 pre-7e memory-only clear + len>=32 token 檢查**（FIXME 標記完整兩階段 commit + audit writeback 未接線）。共用 `disable_edge_predictor_all_impl` 讓 `handle_paper_command` 單元測試路徑與生產 dispatcher 路徑共享同一份邏輯源。
- **`event_consumer/mod.rs`**：dispatcher 在 pipeline_cmd_rx 分支 match 截獲 `DisableEdgePredictorAll` 變體 → `handle_disable_edge_predictor_all(..)` 完整簽名呼叫；其餘變體走 `handle_paper_command`。

**為何拆骨架**：原始 combined WIP 含 Phase 2A adopt + Step 7e 完整兩階段 + 3 新測試。為讓 Phase 2A 能以清潔 commit review，先把 Step 7e 的介面擴展 + getter + handler 入口拆成骨架 commit，完整兩階段邏輯與測試留給下一 commit（FIXME 明確標記）。

**測試**：lib test count 不變 baseline（`test_disable_edge_predictor_all_clears_slots` 更新加 `operator_token`+`reason` 欄位後仍通過 memory-only fallback）。

**下一步**：Step 7e 完成 commit = 填 `_db_mode`/`_audit_pool` 的 FIXME：Stage 1 `write_toml_atomic_fsynced(risk_config, persist_path)` fail-abort → Stage 2 `ConfigStore::apply_patch(Operator, ...)` → Stage 3 `EdgePredictorStore::clear_all()` → V014 `predictor_disabled_all` audit row（token sha256 + reason + cleared_slots + engine_mode，fire-and-forget `tokio::spawn`）+ 3 新回歸測試（reject short token / memory-only fallback / Stage 1 TOML 落盤）。

---

### EDGE-P3-1 Step 7d — `write_toml_atomic_fsynced` SIGKILL durability 回歸（2026-04-15）

**背景**：Step 7e kill-switch 兩階段 commit 要落盤 `use_edge_predictor=false` 的 TOML 狀態；若程序在 OS page-cache 未刷時崩潰/被殺，狀態會丟 → 半啟用殘局。`write_toml_atomic_fsynced()` helper（`config/store.rs:261-291`）於 Phase A 已實作（tmp fsync → rename → 父目錄 fsync），但耐久性只靠 roundtrip unit test 間接驗證。本 step 補齊 spec **T23 / CC #13** 要求的 SIGKILL 對抗測試 —「helper 返回後，進程立刻 SIGKILL，TOML 內容必須已落盤」。

**交付**（1 file +130）：
- **`config/store.rs` tests 模組尾端**：新增 `test_write_toml_atomic_fsynced_survives_sigkill`（`#[cfg(unix)]`）。
  - **測試模式**：`current_exe()` 自我 spawn + env-var 閘控 child 分支（`OPENCLAW_FSYNC_SIGKILL_CHILD`）。Child = 寫 TOML（`use_edge_predictor=false` / `shadow_mode=false` / `note`）→ 寫 marker 檔標記 helper 已返回 → 進入 500ms-sleep idle loop 等死。Parent = 以 `Command::new(current_exe())` + `survives_sigkill` substring filter + `stdout/stderr = Stdio::null()` spawn self，poll marker（10s 超時 + 先殺後 panic 以避免 zombie），`Child::kill()`（unix 上對應 SIGKILL）+ `wait()` 回收，讀檔驗三個 assert（兩個 flag + note field）+ 驗 `.toml.tmp` 伴隨檔 rename 後消失。
  - **為何 substring filter 不用 `--exact`**：`--exact` 要求完整模組路徑（`config::store::tests::test_...`）；模組一移就壞。用 `survives_sigkill` 這個跨 crate 唯一的尾綴 substring 更穩。
  - **為何 `#[cfg(unix)]` 閘控**：Windows 無 SIGKILL 語義，部署目標 linux + macOS 皆 unix。

**測試**：lib **1285→1286**（+1 T23）· core 372 · e2e 35 · **total 1692→1693 pass / 0 fail**。新測試單獨跑 ~50ms（child spawn + poll + SIGKILL + reap）。

**未覆蓋**：T23 spec 附帶「CI 跑 `strace -e fsync` 驗證 syscall 觸發」屬 CI 層檢證，非 Rust 測試層責任（已記錄待 DevOps CI 加 job）。`test_disable_all_survives_sigkill` 整合測試（CC #13 整合級，涵蓋 `DisableEdgePredictorAll` 完整流程）屬 Step 7e 範圍（handler 目前僅 `clear_all()` 不寫 TOML；Step 7e 會接兩階段 commit + 用本 helper）。

**下一步**：Step 7e `DisableEdgePredictorAll` 兩階段 commit（U4）+ V014 `observability.engine_events` audit row，會首次把本 helper 接到實際 kill-switch handler。

---

### EDGE-P3-1 Step 7a — DecisionFeatureSnapshot Rust-direct writer（2026-04-15 · commit d73addb）

**背景**：EDGE-P3-1 Stage 0 需即刻採集 17 維訓練特徵至 `learning.decision_features`（V017 table），但 `use_edge_predictor=false` 仍是預設狀態 — 意味著 gate 走 legacy JS shrinkage 路徑，**不能**靠 predictor 已啟用路徑順帶寫。決策：**Option B**（Rust-direct writer + passthrough IPC 變體）— writer 直寫 DB 繞過 Python consumer（Step 7c 才走 Python），IPC 變體保留做日後 Python 端可選擇消費的跳板。

**交付**（11 files +899/-21）：
- **`edge_predictor/features.rs`**：凍結 `FEATURE_NAMES_V1: &[&str; 17]` + `FEATURE_SCHEMA_VERSION = "v1"`，`feature_schema_hash()` / `feature_definition_hash()` 以 `OnceLock` 緩存 sha256 首 16 hex（Stage 0 兩 hash 相同；Stage 2 ML-MIT 才分離）。6 unit tests（確定性 / 長度 / 非空 / version 常量 / getter 一致 / 名單完整）。
- **`database/mod.rs` + `database/decision_feature_writer.rs`（新 250 行）**：`DecisionFeatureMsg` 10 欄 struct + `run_decision_feature_writer()` async 迴圈（mpsc drain → HashMap dedup by context_id → `flush_features()` 拒絕 `ts_ms=0`（DB-RUN-6 對齊）+ 一次 `serde_json::from_str` JSONB 校驗 + `INSERT INTO learning.decision_features ... ON CONFLICT (context_id) DO NOTHING`）。6 unit tests（dedup / epoch-0 拒絕 / 畸形 JSONB / 合法 parse / SMALLINT side 轉型 / SQL 欄位鎖）。
- **`tick_pipeline/mod.rs`**：新增 `PipelineCommand::DecisionFeatureSnapshot { 10 fields }` 變體 + `TickPipeline.decision_feature_tx: Option<Sender<DecisionFeatureMsg>>` + `set_decision_feature_tx()` 同時傳 IntentProcessor（producer）+ 存本地供 handler 讀取（IPC passthrough），`debug_assert!` 防雙注入。
- **`intent_processor/mod.rs`**：`emit_decision_feature_snapshot()` 於 `evaluate_predictor_gate()` **頂端**呼叫（**早於 `use_edge_predictor` 短路檢查**），僅 `features: Some + context_id: 非空` 時發射。`ts_ms=0` 源頭略過；`try_send` best-effort（full/closed → warn+drop）；tx 未接線 → 靜默 no-op。採集路徑不受 predictor 啟用/禁用狀態影響。
- **`event_consumer/{types,mod,handlers}.rs`**：`EventConsumerDeps.decision_feature_tx` 欄位 + `run_event_consumer` destructure + wire-up 呼叫（`set_shadow_fill_tx` 後） + handler 匹配臂（讀 `pipeline.decision_feature_tx()` 構 msg → `try_send` → Full/Closed warn、no-tx info）。3 handler 穿透測試。
- **`tasks.rs`**：`spawn_db_writers` 4→5 tuple，新增 `channel(1024)` + `run_decision_feature_writer` spawn。Pool 不可用時早 return 5-tuple of None。
- **`main.rs`**：5-tuple destructure + paper/demo/live 三個 `EventConsumerDeps` 構造點注入 `decision_feature_tx.clone()`。
- **`intent_processor/tests.rs`**：4 新發射測試（預測器禁用仍發射 / 空 context_id 不發射 / None features 不發射 / ts_ms=0 不發射）。

**測試**：lib **1264→1285**（+21：6 hash + 6 writer + 3 handler + 4 emission + 2 零碎）· core 372 · e2e 35 · **total 1671→1692 pass / 0 fail**。

**下一步**：Step 7b `ReloadEdgePredictor` IPC（Python route 沿用 `ReloadRiskConfig` 授權）· Step 7c `EmitShadowFill` Python consumer（Option B 對照處理，寫 `learning.decision_shadow_fills`，DB CHECK `engine_mode='paper'`）· Step 7d-7f（`write_toml_atomic_fsynced` / `DisableEdgePredictorAll` 兩階段 / `GET /capabilities`）。5 條餘項可獨立前推，不 blocked。真 unblock = ML-MIT #26 首 ONNX。

### ENGINE-HEAL — 引擎自癒 4 Fix（2026-04-14）

**背景**：2026-04-14 事故 — Rust 引擎靜默死亡 18 分鐘無自動重啟、無死前日誌、ws tick 死前 14+ 分鐘已斷但進程仍「存活」。**交付 4 道 fix**：**Fix 1 panic hook**（`main.rs` L55-108，`std::panic::set_hook` 捕 thread id/location/payload/backtrace + flush → tracing::error，覆蓋所有 tokio worker & std thread，結構化輸出）；**Fix 3 crash-only**（`run_pipeline_crash_only<F>()` 包 paper/demo spawn + Live thread catch_unwind 後補 `live_cancel.cancel()`，任一 panic → 廣播 `Crashed(kind)` + cancel 全局 → ordered shutdown → exit，**不嘗試 isolate 繼續**）；**Fix 4 WS tick stale 自救**（`main.rs` L1108-1155，30s 週期檢查 `shared_last_tick_ms`，age > 120_000ms 且 last!=0 → `cancel.cancel()`，業務層存活斷言防殭屍進程）；**Fix 2 watchdog 自動重啟 + 4 道保險**（`engine_watchdog.py` + `stop_all.sh` + `restart_all.sh`）：(1) `fcntl.flock(/tmp/openclaw/watchdog.lock, LOCK_EX|LOCK_NB)` 多實例防重入 (2) `/tmp/openclaw/engine_maintenance.flag` operator 意圖守則（stop_all.sh 建，restart_all.sh 清）(3) SIGTERM-first + 5s graceful + SIGKILL fallback 避免寫 paper_state.json 中途被殺留損毀 tmp (4) 指數退避 [60,120,300,600,3600]s + `MAX_CONSECUTIVE_FAILURES=5` 熔斷寫 `canary_events.jsonl`。**Bonus**：`rotate_engine_log()` mv 舊 engine.log 到 `/tmp/openclaw/engine_logs/engine-<epoch>.log` 保留 10 份 — Phase 0 發現 `restart_all.sh` 之前用 `>` truncate 是事故放大器，**沒它任何事故都會沒死因**。**決策**：D1 全部 crash-only 含 Live（isolate 會讓三引擎共享的 `RiskConfigStore` 污染帶病繼續交易）· D2 WS stale 120s（60s 誤報太多，worst case ~3min zombie 可接受）· D3 Phase 0 medium（30min 讀 journalctl + grep exit 路徑）。**驗證**：Rust lib 1144 + core 366 + e2e 33 = **1543** pass · 0 fail（與 pre-fix baseline 一致）· watchdog 8/8 unit checks · `bash -n` clean。**留尾**：運行中引擎仍 pre-fix binary（operator 需 `restart_all.sh --rebuild` 部署） · Task #8 殭屍 `openclaw-trading-api.service` 1074+ 次 restart 循環 · env 可覆蓋 stale threshold / per-tier threshold / metric export 為 Phase 2。Worklog：`docs/worklogs/2026-04-14--engine_self_healing.md` + KnownIssue：`docs/known_issues/2026-04-14--ws_stale_detector.md`。

### WP-F/UX-07~10 術語統一 + Live 雙態註解（2026-04-14 · commit 19a84da）

**背景**：GUI 11 個 tab 對 Paper / Demo / Live / Session 有 4+5+6+5 個中文變體共用（纸上交易 / 模拟交易 / 模拟引擎 / 测试引擎 / Bybit Demo 执行引擎 / Demo 引擎 / 实盘交易 / Session Halted / Paper Trading Session / AI 推理会话 / 交易会话 …），tab bar label vs 內部 `<title>` 11 個中僅 1 個一致。**規範字典**：`Paper 模拟` / `Demo 演示` / `Live 实盘` 全域統一；Tab bar `中文 English` 雙語格式。**Session 語境消歧**：Paper Trading Session → Paper 会话；Demo Session Controls → Demo 会话控制；AI 推理会话 / Session History → AI 推理 / AI 推理历史；Session Halted → 交易暂停 Trading Halted；governance 交易会话 → 授权租约 Lease。**Pass-4 Live 槽雙態註解**（Phase 6 Live-Demo 虛擬 key 設計）：tab-live.html L178-188 新增雙語資訊區塊，明確「Live 槽可填入 Mainnet API 或 Live-Demo 虛擬 key（後者跑 Demo 服務器但走 Live 代碼路徑），兩者統一走 Live 最嚴標準（紫色主題 / Global Mode Gate / 二次確認 / 完整風控棧）」；tab-settings.html L773 Live-Demo key 卡片補 `⚠ Live-Demo 等同 Live 待遇` 行。**執行**：3 sub-agent 平行派發（Group A console+system+strategy+risk 4 檔 / B ai+governance+settings+live+governance-tab.js 5 檔 / C paper+demo+learning+monitoring+phase4+app.js+common.js 7 檔）+ 主會話 E2 補修 legacy `index.html`（`legacy_routes.py` 仍 serve）。console.html `BUILD_TS` `20260410.live-ui-v2` → `20260414.ux07-unify-v1` 強制 iframe 緩存刷新。**零後端改動**：所有 JSON API 鍵 / CSS class / 函數名 / endpoint / data-\* 屬性未觸碰，純展示層。16 文件 +160/-143 行。E2 grep sweep 確認無 user-visible 殘留舊詞（僅 JS/CSS 註釋保留）。

### QoL-1 PaperState 重啟還原 + QoL-3 PyO3 統一部署（2026-04-14 · commits 22a0b36+ea25844 · c510388+dc2eec3）

**QoL-1**：引擎重啟後 `paper_state.total_realized_pnl / total_fees / trade_count` 歸零導致 GUI 累計 PnL 卡片失真。**方案**：`PaperState::restore_from_db(pool, engine_mode)` 按 `engine_mode` 從 `trading.fills` 聚合（`COALESCE(SUM(fee),0)` / `COALESCE(SUM(realized_pnl),0)` / `COUNT(*) FILTER (WHERE realized_pnl <> 0)` — 只數 close leg 避免 open/close 雙記）；`apply_restored_counters()` 純函數 helper 重建 `balance = initial_balance + pnl_sum - fees_sum`。新增 `event_consumer/paper_state_restore.rs`（81 行）fail-soft glue（None pool → info / SQL err → warn / 成功 → info with values，引擎永遠能啟動）。三引擎按 `engine_mode` 隔離：demo=-3.49/29.11/254 · paper=-14.40/58.21/333 · live=0/0/0 重啟驗證 PASS。**QoL-3**：`maturin develop` 一次一個 venv 容易漏，每個 venv 觸發完整編譯。**方案**：`helper_scripts/build_pyo3.sh`（285 行）改用 `maturin build` 生 wheel → `pip install --force-reinstall --no-deps` 雙寫 `~/.venv` + `control_api_v1/.venv`。跨平台：`stat -c/-f` dual fallback / bash 4 guard / `mktemp -d -t`。Exit codes 0 ok / 1 args / 2 build / 3 install / 4 verify。`restart_all.sh` 新增 `--rebuild` 旗標（任意位置），build 失敗 exit 2 不啟動服務。**Scope 注意**：`--rebuild` 只重建 PyO3 `.so`，**不重建** `openclaw-engine` binary。**執行**：git worktree 隔離兩 E1 平行完成，QoL-3 先合（純腳本零運行風險）→ QoL-1（需 rebuild + restart）。E4：engine lib 1136 → **1144**（+8 來自 `apply_restored_counters` helper + fail-soft glue unit tests）·Rust 總計 1535 → **1543**。Worklog：`docs/worklogs/2026-04-14--qol_1_and_qol_3_delivery.md`。

### ORPHAN-ADOPT-1 Phase 1 — Reconciler 孤兒主動平倉（2026-04-14）

**背景**：Reconciler seed 完成後對 orphan 倉（Bybit 有倉、baseline 無追蹤）「偵測但不動作」，只有 burst ≥5 drifts 連續 2 cycles → CircuitBreaker + CloseAll 才清。單個 orphan 會留在交易所自生自滅（無止損、funding 累積）直到 operator 手動干預。**交付**：新增 `position_reconciler/orphan_handler.rs`（~350 行 + 11 unit tests）純函數 `handle_orphan(ctx) -> OrphanDecision`，按 A1→A4→B1→default 順序評估：A1 距強平 < 10% / A2 已 CB / A3 名義 > `max_order_notional_usdt`（0=disabled）/ A4 不在 scanner active universe / B1 五策略 shrunk_bps 全非正且 unrealised > 0 → SoftLockProfit / default → SoftConservative。**執行**：Phase 1 所有 decision 走 `PipelineCommand::CloseSymbol { symbol, hint_is_long, hint_qty }` reduce_only，dispatch 失敗回退 drift 讓 Phase 6 升級階梯兜底。**防 spam**：`ReconcilerState.pending_orphan_closes: HashMap<String, u64>` + 2 分鐘 TTL dedup + opportunistic GC。**Per-engine 接線**：`main.rs` `build_orphan_cfg(engine_key)` closure factory 按 engine 綁 `PerEngineRiskStores.select()` + `SymbolRegistry` + `EdgeEstimates` Arc，`spawn_position_reconciler` 多 `orphan_handler_config: Option<OrphanHandlerConfig>` 參數（None=disabled）。`run_position_reconciler` 重構：直接調 `pos_mgr.get_positions()` 保留 raw `Vec<PositionInfo>`（需 liq/mark/unrealised 三字段），`process_orphans()` helper 在 drift classification 後、`evaluate_actions` 前過濾處理。**Audit**：V014 event `orphan_handled`，config_name `reconciler.orphan_handler`。**Phase 2 延後**：真實 Adopt 路徑（合成 StrategyId + paper_state 注入 + StopManager 綁定）等 G-1 R-02 Strategist Agent；`OrphanDecision::Adopt` enum variant + `OrphanStage::SoftAdoptEligible` 分支已預留。**測試**：58 reconciler tests（47 pre-existing + 11 新 orphan_handler unit tests）+ 1136 engine lib + 366 core + 33 e2e = 1535 Rust pass · 0 fail。

### OC-5 FundingArb Complete + WP-F GUI Quick Wins（2026-04-13）

**OC-5 FundingArb** — Full `on_tick()` implementation replacing stub. **Data pipeline**: `index_price: Option<f64>` added to PriceEvent → WS tickers `indexPrice` extraction → `TickPipeline.index_prices` HashMap cache → `TickContext.index_price`. **Strategy logic** (~280 lines): entry evaluation (funding_threshold + edge calculation with amortized costs + basis risk check via `|perp/index - 1|` + H0/cooldown/position guards) → direction (positive rate → short, negative → long) → confidence scaling (capped 0.6) → RC-04 rejection rollback. Exit on rate flip / basis breach / max hold. 22 new tests. TOML configs: paper/demo `active=true` (relaxed thresholds), live `active=false` (conservative). **WP-F GUI**: D-01 `applyAIAdvice()` → clipboard copy; AH-05 `btn-apply-ai` element added to tab-risk.html; UX-06 loading state for all `saveProviderKey()` (6 buttons) + `saveAIConfig()` in tab-ai.html. `tick_pipeline/mod.rs` compacted to stay under 1200-line limit. E2 PASS. E4: 1105 lib + 33 e2e = 1138 Rust · 0 fail.

### R-06-v2 Agent Value Delivery — Learning Loop Closure（2026-04-13）

**Deep analysis rejected original R-06** (100% plumbing, 0% value) → redefined as R-06-v2 "Agent Value Delivery". **Step 2: Analyst→DB→Strategist feedback** — `persist_analyst_feedback()` writes winning/losing patterns to new `learning.pattern_insights` table; `get_feedback_section()` reads patterns + Guardian rejection stats → appended to Strategist Ollama prompt. **Step 3: Guardian rejection stats** — queries existing `trading.risk_verdicts` JOIN `trading.intents` for per-strategy reject_rate (Rust already writes verdicts). **Step 1: Executor IPC bridge** — `_paper_engine=None` (broken since DEAD-PY-2) → `_execute_via_ipc()` fallback to Rust engine `SubmitOrder`; `_shadow_mode=True` default (log only, no actual trade, avoids Path A/B conflict). **Step 4: Conductor stub→real** — `_handle_conductor()` now calls real `Conductor.get_agent_health()` + degraded agent detection (was static "maintain_current"). **New files**: `ai_service_feedback.py` (~170 lines) + `V016__learning_feedback_loop.sql`. ai_service.py 1195→1195 lines (net 0 via docstring compaction). executor_agent.py +115 lines (513→628). **Not done**: fire-and-forget IPC, Conductor health polling, Rust→scout_scan (all zero-value). E4: 1091 Rust lib · 2852 Python · 0 fail.

### EDGE-P2-1 Close Fill Labeling Fix（2026-04-13）

**Root cause**: `emit_close_fill()` unconditionally wrapped ALL close fills with `strategy_name: format!("risk_close:{reason}")` — including strategy-driven closes. This inflated the apparent risk-forced exit count (327/435 in demo), making it impossible to distinguish strategy exits from risk checks. **Fix**: `close_tag` parameter is now written directly as `strategy_name` — callers pass prefixed tags: `strategy_close:*` / `risk_close:*` / `stop_trigger:*`. order_id changed from `risk_close_{em}_…` to neutral `close_{em}_…`. `realized_edge_stats.py` updated to recognize all three prefixes. Diagnostic SQL script added: `helper_scripts/db/close_fill_analysis.sql`. 5 files changed. E4: 1091 lib + 33 e2e = 1124 Rust · 0 fail.

### G-SR-1 Session 7 — C1-C2 Agent 接線 + PM 端到端驗收 COMPLETE（2026-04-13）

**C1 Analyst wiring** — `_handle_analyst()` 從 stub 升級為接入 AnalystAgent.analyze_trade()：IPC trade_data → TradeRecord 構建 → asyncio.to_thread() L1 分析 → 返回 strategy_metrics + strategy_rankings；agent 不可用時 stub fallback。**C2 Scout wiring** — `_handle_scout()` 接入 ScoutAgent.get_recent_intel()/get_recent_alerts()：IntelObject/EventAlert 序列化為 JSON-safe dicts + symbol 過濾；agent 不可用時 stub fallback。**Injection** — `create_ai_service_listener()` 新增注入 ANALYST_AGENT + SCOUT_AGENT from strategy_wiring（fail-open）。conductor_evaluate 仍為 stub（W23+ R-06）。MODULE_NOTE 精簡（bilingual 合併 -36 行）。ai_service.py 1080→1195 行（+115 net，MODULE_NOTE 精簡抵消新增）。**PM 驗收 6/6 PASS**：(1) PersistenceTracker 3 策略 check()/clear()/Close 免檢 (2) Grid 趨勢冷卻 ADX+Hurst 1x-6x (3) Confluence 4 分量 65 分 + qty 調整 (4) Strategist DB→IPC→Ollama→validate 全鏈路 (5) Guardian L1 分類+MessageBus 中繼 (6) C1-C2 注入+真實調用+fallback。**G-SR-1 計劃全部完成**（7 Sessions，Phase A+B+C）。E4: 1086 lib + 33 e2e = 1119 Rust · 2852 Python · 0 fail。

### G-SR-1 Phase B Session 6 — B2+B3+B4 Agent 真實接線（2026-04-13）

**B2 ai_service.py stub→real wiring** — `_handle_strategist()` 接入 Ollama param tuning（build prompt from metrics + current_params + param_ranges → JSON param recommendations，asyncio.to_thread 非阻塞）；`_handle_guardian()` 接入 Ollama event classification（risk_level low/medium/high/critical + assessment，informational only NOT trade blocking）；OllamaClient lazy singleton + fail-closed（unavailable→retain current params / input severity）。**B3 Rust IPC enhancement** — `evaluate_cycle()` 移動 `fetch_current_params()` 至 IPC 前，`current_params` + `param_ranges` 包含在 `strategist_evaluate` 負載，Python 可基於上下文做更好推薦。**B4 Guardian L1 MessageBus relay** — high/critical 事件通過 MessageBus 中繼給 Strategist（fail-open）；`create_ai_service_listener()` 注入 `MESSAGE_BUS` from strategy_wiring。ai_service.py +350 行（730→1080）；strategist_scheduler.rs +22 行（692→714）。B-E2 10/10 PASS · B-E4 1083+33=1116 Rust · 2852 Python · 0 fail · B-E5 PASS。

### G-SR-1 Signal Tightening Phase A Session 1+2（2026-04-13）

**Phase A S1: A0 基礎模組提取** — `grid_helpers.rs` 純函數提取（build_linear_levels/build_geometric_levels/nearest_grid_idx/compute_ou_step/rebalance）+ `confluence.rs` 共享模組（PersistenceTracker + compute_score 4 分量 65 分制 + score_to_qty_pct 5 段平滑插值 + ConfluenceConfig 三配置 trend/reversion/breakout）。

**Phase A S2: A0-c + A1 + A2 + A3** — A0-c：3 策略 TOML Params struct 加 confluence 字段（serde(default) backward compat）+ build_confluence_config() + StrategyFactory 接線 + R4-7 update_params rebuild。A1：PersistenceTracker.check() 時間制過濾器接入 ma_crossover/bb_reversion/bb_breakout entry path（MA/BBR 120s, BBB 60s），close 免檢 + clear() 清理。A2（提前實施）：weighted confluence scoring（trend 25/20/12/8, reversion 15inv/30/10/10, breakout qty-only 10% 底線），冷啟動 adx&&rsi None→全倉退化，min_notional guard。A3：Grid trend-adaptive cooldown（ADX 60% + Hurst 40%, 1x-6x 動態倍率，3 TOML 參數）。修復：bb_reversion 測試加 ADX 數據、dead `make_entry_intent()` 刪除、stress test pub 可見性、BbBreakoutParams TOML struct 補齊。Engine lib 934→1024 tests（+90），e2e 29→33（+4）= 1057 total, 0 fail。

### 04-12 審計修復 Wave 2：14 角色報告逐一核實 + 代碼修復（2026-04-12）

**A3 GUI 可用性審計全修** (commit `fd0bc45`)：CRITICAL×2 + MAJOR×14 + MINOR×18 + SUGGESTION×2 一次性全修。關鍵：Live/Demo/Paper 持倉「平倉」按鈕確認流程 + 空狀態提示 + 響應式間距 + 按鈕排列一致性。

**QC 量化審計全修** (commit `e03421f`)：Session 3.3+3.3b — 12 hardcoded 參數移至 TOML + 7 risk gap 修補 + 10 action items 全部解決。

**P2 FIX-08 超限文件拆分** (commit `50d7a4b`)：12+ 超過 1200 行硬上限的文件拆分（governance_routes / strategy_ai_routes / paper_trading_routes / strategy_read_routes / strategy_wiring / experiment_routes / live_session_routes / evolution_routes / backtest_routes）。

**P2 FIX-23/34/35/57** (commit `0de58bb`)：FundingArb 策略註冊 + outcome backfiller DDL + budget sync 修復。

**E3+CC 安全/合規修復** (commit `f8685bf`)：5 fixes + 2 報告更新 — Cookie secure flag + HMAC edge cases + error disclosure。

**E5+MIT 報告核實** (commit `c73a3f2`)：5 code fixes + 2 report corrections — 補漏 push_capped 缺失 + budget tracker sync。

**E5 審計收尾** (commit `6e2a01e`)：3 remaining items implemented + P-08 test fixed。

**FA 審計修復** (commit `d16ed08`)：3 orphan Rust files 刪除（batch_order_manager/leverage_token_client/spot_margin_client）+ handlers.rs 拆分 handlers_config.rs + PIPELINE_BRIDGE 死碼清理。

**AI-E 審計報告校正** (commit `4d427f5`)：18 inaccuracies corrected（3 Serious / 8 Medium / 7 Light — 均為報告錯誤非代碼 bug）。

**BB Bybit API 審計驗收** (commit `50a4b1e`)：7/7 P1 全部關閉 — 最終核實 worklog。

### E5 Performance Optimization — 23 items（2026-04-12）

P-01 `push_capped<T>()` ring buffer utility（13+ 重複消除）· P-02 PriceEvent 5 structured fields · P-03 hot-path structured reads · P-04 `now_ms()` utility · P-05 `is_stale()` utility · P-06 WS subscriptions Vec→HashSet O(1) · P-08 `TickContext<'a>` zero-copy borrowed refs（5 strategies + orchestrator）· P-09 Arc<RiskConfig> bind-once · P-10 parallel async DB flush `tokio::join!` 7 tables · S-01 confidence clamp · S-02 ring-buffer dedup（+E2 residuals）· S-03 `build_intent()` · S-04 timestamp centralize（+E2 residual）· R-01~R-05 naming（`ShadowOrderRequest`→`OrderDispatchRequest` 等）· D-01/D-03 dead method removal。P-07 skipped（WS SDK managed）· S-05 skipped（fail-closed）· D-02 deferred（HashMap removal post-migration）。17 files changed, +563/-899, net -336。E4: 934+366+27 = 1327 pass 0 fail。

### 審計 P2 Batch A+B：10 項快速修復（2026-04-12）

FIX-21 lib.rs 3 孤立模組移除（batch_order_manager/leverage_token_client/spot_margin_client）· FIX-38 CLAUDE.md §九 Singleton 表補登 6 項（_pool/DEFAULT_LEASE_TTL_CONFIG/_backtest_engine/_scheduler/_evolution_engine/_ledger）· FIX-41 Bearer Token panel 死碼清除（index.html/app-gui.js/app-review.js/styles.css）· FIX-44 tab-learning/monitoring/strategy 加載失敗狀態 UI · FIX-45 Live tab 刷新 30s→15s · FIX-46 tab-risk.html 已達標（510 行，無需拆分）· FIX-51 3 DEPRECATED 文件移至 archive/ · FIX-53 docs/README.md 補 4 子目錄索引 · FIX-54 CHANGELOG 缺失 commit 補錄 · FIX-56 Layer2 定價日期 2026-03-27→04-12。

### PNL-FIX-1/2 + 3 項重要中間修復（2026-04-12）

**PNL-FIX-1** (commit `2a422fa`)：`on_tick.rs` 5 條 close 路徑誤用 `event.last_price` 跨 symbol 平倉 → 改用 per-symbol latest_price。**PNL-FIX-2** (commit `cbb4e45`)：`emit_close_fill` 寫 `fee: 0.0` → 所有平倉路徑收真實費用。**Circuit Breaker 修復** (commit `6ae6e1b`)：3 fixes 防止誤觸 CB + spam。**EA-Persist** (commit `0255a35`)：execution_authority 統一至 T0 trust persistence。**Paper/Demo Session Split** (commit `986d724`)：Paper/Demo 獨立 session 控制。

### 3E-ARCH 中間修復合集（2026-04-11~12）

(commit `d670759`) cross-pipeline DB ID 碰撞修復 — ID 嵌入 engine_mode。(commit `f6e7afc`) paper_state 啟動時從交易所快照 seed。(commit `b5e45f7`+`8e08c34`) private WS topic 環境感知修復。(commit `152d1f6`) demo DCP topic 移除 + live worker_threads 2→4。(commit `660cb75`) scanner/deployed 顯示 Rust active symbols。(commit `87bbe66`) live-gui 條件單顯示 + per-engine session/metrics。(commit `9853845`) paper-metrics 改用 Rust 權威 balance/peak。(commit `35272d3`) IPC 所有命令加顯式 engine 參數修復跨引擎路由。(commit `56c648f`) paper_only 模式 + cost_gate 冷啟動探索。(commit `15203f6`) 動態 is_exchange_mode 防 live WS 覆寫 paper state。(commit `326a191`) 移除 handlePaperAction 硬編碼 initial_balance:10000。(commit `2473efb`+`6bafa4e`) demo/live GUI 平倉路由修復。

### 審計 P2 Rust 7 項修復（2026-04-12 · commit `84f00eb`）

FIX-24 bb_reversion RSI 閾值 30/70→TOML 可配 + ParamRange agent-adjustable · FIX-25 grid_trading fee_rate 字段取代硬編碼常量 · FIX-26 bb_breakout squeeze bool→時間戳 30min 過期 · FIX-27 kelly_sizer 負 edge 拒絕（0.0）非 fallback · FIX-28 intent_processor account_leverage 字段 · FIX-31 PriceEventKind typed enum（Trade/Orderbook/Ticker/Liquidation/PriceLimit/AdlNotice/RestPoll）+ 向後兼容 metadata 雙路徑 · FIX-33 event_consumer exec_id 去重 O(n)→O(1) HashSet+VecDeque。15 files changed, +199/-194。E4: 965+366+27+29+2852 = 4239 pass。

### 全程序鏈審計 P0+P1 全修 + 二輪驗證 + CONCERN 修復（2026-04-12）

**Session 1 (P0 8/8)**：FIX-03 FastTrack ReduceToHalf/PauseNewEntries 實現 · FIX-04 真實 price_drop/margin_util · FIX-09 ocEsc 單引號 · FIX-10 IPC HMAC Live 強制 · FIX-13 edge_estimates +14 tests · FIX-14 REST fail-closed +7 tests · FIX-15 三管線並發 +1 test · FIX-19 execFee taker_fee_rate 估算。

**Session 2 (P1 18/18)**：FIX-05 correlated_exposure_pct 實現 · FIX-06 grid_levels TOML→runtime · FIX-07 OU theta non-OU fallback · FIX-11 Cookie secure auto-detect · FIX-16 startup +5 tests · FIX-17 ConfigStore 並發 +2 tests · FIX-18 Price=0 +2 tests · FIX-20 pre_check_order 刪除 · FIX-22 MlSwitches 4 死欄位刪除 · FIX-29 on_tick 1307→1186 行 · FIX-30 symbol.clone 審查（文檔結論）· FIX-32 risk_config 借用 · FIX-39/40 Danger Zone + 策略刪除 openConfirmModal · FIX-47/48 REFERENCE/KNOWN_ISSUES 更新 · FIX-52 SCRIPT_INDEX 全面重寫 · FIX-55 API paths verified。

**二輪嚴格驗證**：8 組並行 agent 逐行讀碼，26/26 PASS。發現並修復 3 CONCERN：(1) **FIX-03b** ReduceToHalf 缺 `dispatch_close_order()` — Live 模式下本地狀態與交易所倉位脫節 **[HIGH]** → 已補 dispatch；(2) **FIX-19b** 單一 fee rate 近似所有 symbol → 改用 `intent_processor.fee_rate(&symbol)` per-symbol 3 級解析；(3) **FIX-16b** 2/5 tests trivially passing → 替換為 semver 驗證 + env valid/invalid/negative/zero。

**KNOWN_ISSUES**：TRADE-2 → RESOLVED（Rust 同步 tick 無競態）· TRADE-4 → RESOLVED（Rust 每筆 fill 獨立 exec_qty）· 統計修正 OPEN 9 / RESOLVED 15。

965 engine lib + 5 bin + 29 e2e = 999 tests · 0 failures。

### Earned-Trust TTL Ladder + Audit Trail 時間戳修復（2026-04-12）

(1) **Audit Trail 時間戳修復**：`tab-governance.html` JS 讀 `r.timestamp` 改為 `r.when_ms || r.when*1000`，修復 Audit Trail 時間欄永遠顯示 `'--'` 的 bug。(2) **Earned-Trust 授權 TTL 階梯**：新增 `earned_trust_engine.py`（715 行）— T0(24h)/T1(72h)/T2(168h)/T3(360h) 四層階梯，連續乾淨天數晉升，中途降級即時標記（session 繼續），T3 最多自動續期 1 次後強制 Operator 全面審查；新增 `live_trust_routes.py`（484 行）— 3 端點（GET trust-status / POST renew / POST renew-review）；`live_session_routes.py` 新增 session start/stop 鉤子 + `_grant_execution_authority_internal()` 內部輔助；`main.py` 注冊 `live_trust_router`；`tab-live.html` 新增 Trust Status Bar（tier badge + 倒計時 + 續期卡 + T3 全面審查面板）+ 完整 JS（loadTrustStatus / openTrustRenewCard / submitRenew / submitFullReview）。53 新測試 pass。E4: 2852 Python passed。

### Phase 6 PM 驗收 PASS + TODO 歸檔整理（2026-04-12）

6-09~13 最終驗收週期完成。E4: 935 engine lib + 366 core + 18 e2e + 32 promotion = 1351 passed / 0 failed / 0 warnings。E2: Reconciler 0 BLOCKER 0 MAJOR（pre_escalation_level 文檔建議 MINOR）· Promotion Pipeline 0 BLOCKER 0 MAJOR（governance_routes 超限 pre-existing）。QA: 三引擎存活 + 雙 Reconciler 運行 + baseline seeded + API auth enforced。E5: stress PASS。Phase 6 路線圖狀態從 🟡 升為 ✅。TODO.md 歸檔：晚間 Audit BLOCKERs（B-1/B-2/M-1~4）+ Phase 6 驗收詳情移入 `docs/archive/2026-04-11--completed_todo_w19_w20_phase6.md`；3E-ARCH 折疊內容移除（已有專屬歸檔）；排期表更新 W19-21 ✅；Gap 索引標記 G-3/G-5/G-9 完成。

### GUI 指標 DB 降級 + 顯示修復 4 項（2026-04-12）

(1) Live engine badge 顯示「已暫停」— `get_live_session_status()` 改用 `get_engine_snapshot()` 讀頂層 `paper_paused`。(2) Performance Metrics 全 0 — 新增 `fetch_fills_from_db(engine_mode)` DB 降級讀取，paper 1336 fills / demo 68 fills 正確顯示。(3) Live 掛單 Price/Status 顯示 "--" — `OrderInfo` 新增 `trigger_price` 欄位 + JS snake_case 兼容。(4) Demo 夏普比率硬編碼 N/A — 改為從 round-trip PnL 計算。worklog: `docs/worklogs/2026-04-12--gui_metrics_db_fallback_and_display_fixes.md`。935 engine lib + 366 core + 22 paper_metrics pass。

### 3E-ARCH GUI 路由修復：Paper tab 顯示 Live 引擎數據（2026-04-11）

3E-ARCH 上線後 Paper GUI tab 顯示 ~$612 餘額且持倉表為空，實際 paper 引擎是 ~$9941 / 9 倉位。**根因**：`main.rs:563-708` `is_primary` 優先序為 Live > Demo > Paper（`paper.is_primary = !has_live && !has_demo` / `live.is_primary = true`），三引擎並行時 Live 寫入 compat `pipeline_snapshot.json`；而 Python `RustSnapshotReader.get_paper_state()` / 多數 helper 預設讀 compat 檔，因此 paper 路由全部讀回 Live 數據。**On-disk 驗證**：四份檔案內容正確獨立，bug 純粹在 Python 路由層。**修復**：(1) `ipc_state_reader.py` `get_paper_state(mode/engine)` 預設透過 `get_engine_snapshot("paper")` 讀 `pipeline_snapshot_paper.json`；`get_snapshot()` 新增可選 `engine=` 參數（保持預設讀 compat 以維持單元測試 / 單引擎部署兼容）。(2) `paper_trading_routes.py` 9 個 call site 改為顯式 `engine="paper"` / `mode="paper"` + `is_engine_available("paper")` 取代 `is_available()`（涵蓋 session/status、positions、pnl、orders、fills、metrics、export、market-feed/status、shadow/decisions、audit-trail、resume）。(3) `risk_routes.py` 3 個 call site 改 `engine="paper"`（風控儀表板讀 paper 引擎 drawdown/balance/gate stats）。(4) `strategy_read_routes.py` intent reader 改 `mode="paper"`。(5) `live_session_routes.py` fills 降級分支改 `mode="live"`。**回歸測試**：`test_ipc_state_reader.py` 新增 `TestPerEngineRouting`（6 tests）覆蓋三引擎並存路由矩陣，使用 11111.11/22222.22/33333.33 三組哨兵餘額（class 級常數 + docstring 標明刻意用假數值）。**驗證**：21/21 ipc_state_reader + 39/39 ipc_integration + 80/80 paper_live_gate/paper_metrics passed。Reader 直接讀真實 `/tmp/openclaw/pipeline_snapshot_*.json`：`get_paper_state()` 預設返回 9941.47 / 9 倉位（之前是 612.95 / 0 倉位）。

### 3E-ARCH 持久化修復：with_kind() 漏設 pipeline_kind 字段（2026-04-11）

MEGA-BLOCKER-0 commit 0f3af65 留尾 bug：`TickPipeline::with_kind()` 只設 `governance` 不設 `pipeline_kind`，三個引擎全部留在 `with_balance()` 預設的 `PipelineKind::Paper`，導致 demo/live event_consumer 在 `kind_tag = pipeline.pipeline_kind.db_mode()` 時都返回 `"paper"`，三引擎 StateWriter 搶寫同一份 `paper_state.json` / `pipeline_snapshot_paper.json`，產生大量 `state rename failed` ERROR；watchdog 因此誤報 demo/live "not_running"。**修復**：`tick_pipeline/mod.rs:683` `with_kind()` 補一行 `p.pipeline_kind = kind`。**回歸測試**：`test_with_kind_sets_pipeline_kind_field` 鎖定三個 variant。**驗證**：重啟後 `pipeline_snapshot_paper.json` / `pipeline_snapshot_demo.json` / `pipeline_snapshot_live.json` 三檔案各自獨立寫入（balance 10000/793.97/612.95 對應 Paper 默認/Demo Bybit/LiveDemo Bybit），watchdog 三引擎全 alive，0 persistence errors。930 engine lib pass（+1 regression test）。

### 3E-ARCH L3 審計修復：e2e 測試 + 21 warning 清零 + 防御性加固（2026-04-11）

L3 全面審計（PM/PA/FA/CC/E3/E4/E5/MIT/QC 9 角色並行）發現並修復所有問題。**P0**：`stress_integration.rs` 6 個編譯錯誤修復（StrategyAction enum 適配 + IntentProcessor 5th arg GovernanceProfile）。**P2 防御性加固**：(1) event_consumer D19 安全斷言（交易所管線禁止寫入 market/feature DB）；(2) 快照去抖間隔按引擎錯開（Paper 5s/Demo 5.5s/Live 4.5s）避免 I/O 爭用；(3) IPC `extract_engine_tx` 無 engine 參數時 debug 提示；(4) startup.rs 憑證記憶體持留文檔化；(5) fan-out channel buffer 非對稱設計文檔化。**P3 代碼清潔**：21 cargo warning 全部清除 — 6 unused imports + 6 unused variables + 4 unreachable patterns（sector 重複分類）+ 2 dead methods（`cost_gate_k` #[allow] / `make_exit_intent` 刪除）+ 2 never-read fields + 1 unused inner import。**INFO**：Python ipc_client.py `mode` → `engine` 參數重命名語義修正。0 warnings / 929 lib + 366 core + 29 e2e + 2792 Python = 4116 tests passed。

### 3E-ARCH MEGA-BLOCKER-0：真正三引擎獨立並行（2026-04-11 · commit e012faa）

完成原始 3E-ARCH Phase C（3E-10.1）設計中未實現的「三個獨立 spawn」。**startup.rs**：新增 `ExchangePipelineBindings` struct + `build_exchange_pipeline()` 按 API key 獨立構建每條交易所管線（DCP/auto-margin/fee/balance/Private WS 全封裝）；刪除 `determine_primary_kind()` / `detect_available_pipelines()` / `fetch_exchange_balance()`。**main.rs**：刪除「primary+alongside」二管線模型，改為三獨立 spawn（Paper 永遠啟動 + Demo 條件 + Live 條件 D17 OS thread）；`Vec<Sender>` 動態扇出取代固定 primary+paper 雙通道；三獨立 IPC cmd channels 全填充 `EngineCommandChannels`；D23 per-exchange Reconciler（Live + Demo 各自獨立）；有序 shutdown Live→Demo→Paper。2 files, +482/-469 行。929 lib + 366 core + 18 e2e pass。

### 3E-E2 Phase G 殘留修復：M-3/M-4 + 8 MINOR（2026-04-11 · commit 910d2bc）

M-3：`on_tick.rs:497,616` GovernanceProfile hardcoded → `self.pipeline_kind.governance_profile()`（Demo 現用 Validation cost_gate）。M-4：Live pipeline 線程加 `catch_unwind` + panic → `Crashed` 廣播 + health=Down；shutdown JoinError panic 記錄而非靜默丟棄。m-1：`handle_get_state()` 合併 2 次 snapshot 讀取為 1 次。m-2：`std::ptr::eq` → `primary_label()` 字串比對。m-3：`determine_primary_kind()` 3→1 次調用。m-5：`.unwrap()` → `.expect()` with context。m-8：`AuditWriter` 新建檔案 chmod 0600。殘留僅 M-1/M-2 文件大小監控。929 lib + 366 core + 18 e2e pass。

### 3E-E2 Phase G: 9 角色重審 PASS（2026-04-11 · commit de222bd）

Phase A-F 修復完成後重跑 9 角色並行 E2 審查（E2/FA/PA/QC/BB/MIT/E3/E4/E5）。結果：**9/9 PASS — 0 BLOCKER / 4 MAJOR（非阻塞）/ 10 MINOR**。原 10 BLOCKER + 7 MAJOR + MEGA-BLOCKER-0 全部確認修復。測試基線：929 engine lib + 366 core + 18 e2e = 1313 passed / 0 failed / 0 ignored。4 殘留 MAJOR：handlers.rs 1195 行近上限、on_tick.rs 1172 行、GovernanceProfile hardcoded（TODO 3E-2b）、無 catch_unwind 包裹 pipeline（Live 前修）。審計報告：`docs/audits/2026-04-11--3e_arch_phase_g_reaudit.md`。

### 3E-E2 Phase F: 5 超限文件拆分（2026-04-11 · commit 26b9926）

BLOCKER-9：5 個超 1200 行硬上限文件拆分為目錄模組。tick_pipeline.rs 3907→mod.rs(1122)+on_tick.rs(1172)+commands.rs(708)+tests.rs(930)。ipc_server.rs 3223→mod.rs(975)+handlers.rs(1195)+tests.rs(1058)。main.rs 2243→main.rs(930)+startup.rs(716)+tasks.rs(488)。intent_processor.rs 1785→mod.rs(493)+gates.rs(204)+router.rs(499)+tests.rs(597)。position_reconciler.rs 1397→mod.rs(617)+escalation.rs(351)+tests.rs(438)。22 files changed, 11645 insertions(+), 11707 deletions(-)。929 lib + 366 core + 18 e2e pass。

### 3E-E2 Phase E: 25 blocker tests（2026-04-11 · commit e0a7451）

BLOCKER-10：補 25 個 blocker 測試覆蓋 D2（startup barrier）、D6（cross-engine events + PipelineHealth）、D15（global notional cap 8 tests）、D23（snapshot versioning 3 tests）。929 engine lib + 366 core + 18 e2e pass。

### 3E-E2 Phase D: Architecture hardening（2026-04-11 · commit e04c974）

3 BLOCKER + 4 MAJOR：BLOCKER-2（D6 三級故障收縮 EngineEvent/PipelineHealth/broadcast）、BLOCKER-3（D15 全局名義值上限 AtomicU64 + check_global_notional_cap）、BLOCKER-4（D17 Live 獨立 runtime std::thread + worker_threads(2)）、MAJOR-2（startup barrier oneshot 60s timeout）、MAJOR-3（有序 shutdown WS→IPC→primary→paper 10s）、MAJOR-5（IPC audit log）、MAJOR-7（snapshot schema_version 2.0.0 + written_at_ms）。

### 3E-E2 Phase B+C: Per-engine TOML + TradingMode deletion（2026-04-11 · commit 41d5a71）

BLOCKER-8（per-engine TOML params）+ MAJOR-4（TradingMode 殘留清除）+ 3E-10.1~10.7（DB dedup / channel rename / D12 audit / Python env var / config 橋接刪除）。`TradingMode` enum 從 Rust 完全刪除（僅保留 config 反序列化過渡）。PerEngineRiskStores + StrategyFactory::create_for_engine()。

### 3E-E2 Phase A: Quick fixes（2026-04-11 · commit a1c3291）

BLOCKER-5（hmac.compare_digest constant-time）、BLOCKER-6（5 處 std::sync::RwLock→parking_lot::RwLock）、BLOCKER-7（API key save lock 串行）、MAJOR-1（StateWriter chmod 0600 + regression test）。

### 3E-5+7+8: Per-engine snapshots + Python cleanup + API key conflict + Paper GUI（2026-04-11）

**3E-5 (S10) Rust**: `DualStateWriter` wrapper in persistence.rs — per-engine snapshot files (`pipeline_snapshot_{paper|demo|live}.json`) + compat `pipeline_snapshot.json` for primary. `EventConsumerDeps` gains `is_primary: bool`. event_consumer derives filename from `pipeline_kind.db_mode()`. +2 tests (DualStateWriter writes both / no-compat).
**3E-5 (S10) Python**: `_get_trading_mode_from_engine()` → `_get_live_engine_kind()` (live routes always query live/demo engine, no single-mode assumption). `ipc_state_reader.py` rewritten: per-engine cache system, `get_engine_snapshot(engine)`, `get_active_engines()`, `is_engine_available(engine)`, backward-compat primary fallback. `paper_trading_routes.py`: `trading_mode` → `pipeline_kind` in session status response. `strategy_ai_routes.py`: docstring updates.
**3E-7 (S11)**: `settings_routes.py` save_api_key: cross-slot conflict detection — same API key cannot be used by two pipelines (409 response). Checks demo↔live/live_demo pairs.
**3E-8 (S11)**: `engine_watchdog.py`: multi-snapshot monitoring — checks all 4 snapshot files, system alive if ANY engine is fresh. `get_watchdog_status()` returns per-engine status. `tab-paper.html`: Initial Balance input field next to Start button (GUI-configurable, fallback to Demo balance). `POST /api/v1/paper/config` endpoint: persists `initial_balance_usdt` to `settings/paper_config.toml`. `GET /api/v1/paper/config` reads it back.
**Files**: persistence.rs (+32), event_consumer/{mod,types,handlers,tests}.rs, main.rs, ipc_state_reader.py, live_session_routes.py, paper_trading_routes.py, strategy_ai_routes.py, settings_routes.py, engine_watchdog.py, tab-paper.html. **Tests**: 896 engine lib + 366 core + 2792 Python passed.

### 3E-3+4: IPC EngineCommandChannels + TradingMode→PipelineKind cleanup（2026-04-11）

**3E-3 (S8)**：`EngineCommandChannels` struct 取代單一 `pipeline_cmd_tx`。Paper/Demo/Live 各自獨立命令通道。`extract_engine_tx()` helper 按請求 `engine` 參數路由。`handle_set_system_mode_broadcast()` 廣播到所有管線。`add_engine_mode`/`switch_engine_mode` IPC handler 移除 + `PipelineCommand::AddMode`/`SwitchMode` 移除。main.rs 接線：primary_cmd_tx + paper_alongside_cmd_tx → EngineCommandChannels。
**3E-4 (S9)**：`PipelineSnapshot.trading_mode` → `pipeline_kind: PipelineKind`（serde rename 向後兼容）。TickPipeline `trading_mode` field → `pipeline_kind`。mode_states/active_modes/set_trading_mode/add_mode 等多模式基礎設施整體移除。event_consumer runtime TradingMode 引用全部替換為 PipelineKind。config/mod.rs TradingMode 保留（`#[deprecated]`）供 config 反序列化過渡使用。5 個死測試移除，1 個新測試。
**文件**：ipc_server.rs（+60/-80）、tick_pipeline.rs（-180 mode switching）、pipeline_types.rs、event_consumer/mod.rs、handlers.rs、main.rs。
**測試**：894 engine lib（-4 死測試 +1 新）+ 366 core pass。

### 3E-2b-β+γ: Per-engine private WS + reconciler engine label（2026-04-11）

**D21**：`spawn_private_ws_supervisor()` 提取為可重用函數。每交易所管線獨立 BybitPrivateWs + ExecutionListener。日誌含 `engine=` 欄位區分管線。原 inline 130 行 → 函數式結構 `PrivateWsBindings` struct + helper function。
**D23**：`run_position_reconciler()` 新增 `engine_label: String` 參數。V014 audit payload 加 `"engine"` 欄位，區分多對帳器輸出。`spawn_reconcile_audit()` + `spawn_action_audit()` + `dispatch_action()` 全部加 label 參數。
**Ordered shutdown**：Paper-alongside handle 加入 shutdown 等待序列。Private WS handles 通過 CancellationToken 自行退出。
**文件**：main.rs（private WS 提取 +80/-130）、position_reconciler.rs（+15 engine_label 貫穿）。
**測試**：898 lib + 18 e2e pass（無新增，重構保守）。

### 3E-2b-α: Pipeline spawn skeleton + bounded fan-out + parking_lot + DB pool（2026-04-11）

**D25**：`default_pool_max()` 5→20，支撐 3 pipeline + 2 reconciler + scanner 並行。
**D12**：`parking_lot::RwLock` 替換跨管線共享的 `std::sync::RwLock`（EdgeEstimates in main.rs/scanner, InstrumentInfoCache）。非中毒語義，避免單管線 panic 級聯崩潰。
**D10/D20**：有界扇出（bounded fan-out）— 單一 WS event_rx → `Arc<PriceEvent>` 廣播到 N 管線。Paper 1024、Demo 1024、Live 512 buffer。`try_send` 延遲檢測。
**Spawn skeleton**：Paper 管線始終啟動。Demo/Live 管線根據 TradingMode 條件啟動（interim，3E-4 改為直接讀 API key）。Paper-alongside 獨立 pipeline_cmd 通道 + risk_level 原子量。共享 DB writer 通道。
**文件**：main.rs（+120/-50）、instrument_info.rs（parking_lot）、scanner/runner.rs（parking_lot）、database/mod.rs（pool max）、event_consumer/types.rs（Arc<PriceEvent>）、order_manager.rs（test fix）、tick_pipeline.rs（+2 fan-out tests）、Cargo.toml×2（parking_lot dep）。
**測試**：898 lib + 18 e2e pass（+2 新 fan-out tests）。

### system_mode GUI→Rust 同步 + 3E-ARCH 計劃 + GridTrading multi-symbol（2026-04-11）

**system_mode 同步**（6 文件實現）：
- `tick_pipeline.rs`：新增 `SystemMode` 枚舉（live_reserved/demo_reserved/shadow_only/observe_only/design_only），`system_mode` 字段，on_tick gate，`set_system_mode()` 方法（自動平倉 + 暫停 paper）
- `pipeline_types.rs`：`PipelineSnapshot` 新增 `system_mode: String`
- `event_consumer/handlers.rs`：`SetSystemMode` handler arm
- `ipc_server.rs`：`set_system_mode` IPC 命令，`get_state` 改從快照讀 system_mode（移除硬編碼 "demo_only"）
- `ipc_client.py`：`sync_ipc_call()` 同步 IPC 輔助函數
- `control_ops.py`：`apply_config_change` 後 push system_mode 到 Rust（盡力而為）
- `live_session_routes.py`：session status 新增 `system_mode` 字段

**GridTrading multi-symbol 修復**（pre-existing 未修復項）：
- 新增 `template_bounds: Option<(f64, f64)>` 字段，3 個構造函數補齊
- 2 個測試適配 HashMap 索引（lines 1053-1055, 1071）

**3E-ARCH 計劃文件**：
- `docs/references/2026-04-11--three_engine_parallel_arch_plan.md`（PM+PA+FA 三角色分析）
- TODO.md 更新：3E-ARCH 段落 + W22 排期 + 關鍵路徑

**測試基線**：engine lib 879 + e2e 18 + Python 2792 / 0 fail

### Multi-Symbol Position Tracking Refactor（2026-04-11）

**問題**：4 策略各持單一全局 `position: Option<bool>`，理論併發上限僅 4 倉，遠低於風控 `open_positions_max=25`。

**修復**：
- MaCrossover / BbReversion / BbBreakout / GridTrading 全部改為 `HashMap<String, bool>` per-symbol 追蹤
- GridTrading `new()` / `new_geometric()` 移除硬編碼 `"BTC"` key + 預填 grid，改為 `template_bounds` 延遲初始化
- `on_tick` 首次收到 symbol 時：有 template_bounds 用模板邊界，否則 ±10% adaptive
- 生產路徑 `new_adaptive()` 行為不變
- 7 個測試適配延遲初始化

**容量**：理論上限 4 → 100（4 策略 × 25 symbols），實際受風控 `open_positions_max` / `max_same_direction` 約束。

**測試基線**：engine lib 879 + e2e 18 / 0 fail

---

### W21 6-04~08 Phase 6 驗收（2026-04-11）

**6-04 集成測試**（reconciler_e2e.rs +11 場景，7→18）：
- S7: MinorDrift 不重設 clean cycle 計數器（對比 MajorDrift 重設）
- S8: SideFlip → Cautious（完整 handler 鏈路）
- S9: Ghost → Cautious（完整 handler 鏈路，E2 P0 fix）
- S10: Per-symbol 30min 冷卻阻止重複升級
- S11: 全局 5min 冷卻限制快速連續升級（含過期後放行）
- S12: 多級恢復全程 Defensive → Reduced → Cautious → Normal
- S13: REST 失敗漸進三階段（10→Cautious / 30→Reduced / 60→Defensive / 已達目標→跳過）
- S14: Floor rule 阻止恢復低於 pre_escalation_level（原 scenario 7 重編號）

**6-05 壓測**：
- Rust S1: 100 cycle 快速漂移/清除交替 — 狀態一致，max Cautious
- Rust S2: 50 symbols 同時漂移 → CB + CloseAll
- Rust S3: 20 輪 handler 快速升降 — 無死鎖
- Rust S4: 1000 次 evaluate_actions 性能 < 100ms
- Python 5 場景：10 線程並發 register/promote（==1 成功）/冪等/100 策略批量 <1s/並發 metrics

**6-06 sync_commit 驗證 PASS**：
- global `ALTER DATABASE SET synchronous_commit = 'on'`（V006:90）已保護 orders/fills
- MIT/CC/FA 三方確認：per-session 分層優化歸 WP Backlog（當前安全方向偏保守正確）

**6-07~08 EvolutionEngine**：
- 保留（不 deprecate）— 用於 DL/AI agent 學習
- EvolutionEngine = 參數網格搜索優化，PromotionPipeline = 策略生命週期管理，職能不重疊

**6-RC-6 TODO 一致性修復**：6-RC 段標記與 W19 段對齊（`[x]`）

**E2 修復 3 項**：
- P0: Ghost scenario 補完整 handler 鏈路驗證
- P1: Python 並發 promote 斷言從 `>= 1` 改 `== 1`（防漏 lock bug）
- P1: Rust make_writer() temp 路徑加 thread id 防並行碰撞

**測試基線**：engine lib 879 + e2e 18 / Python 2792 / 0 fail

### W20 安全審查 + 漸進放權 + CC 合規（2026-04-10）

**SEC-04/06/13 + G-9 E3 深度審查**
- SEC-04（SQL injection）：全 parameterized queries，PASS
- SEC-06（token in JSON）：已修復為 HttpOnly cookie，PASS
- SEC-13（u32 truncation）：已修復為 saturating cast，PASS
- G-9（HMAC dead import）：NOT dead — `hmac.compare_digest()` 用於 auth token 驗證（L171），PASS

**WP-CC/P9 — 交易所雙軌止損接線（原則 #9）**
- `event_consumer/mod.rs`：StopRequest channel consumer 從 log-only 升級為調用 `PositionManager.set_trading_stop()`
- Paper 模式無 client 時優雅跳過；Demo/Live 調用 Bybit `POST /v5/position/trading-stop`
- Fail-closed：API 失敗時 warn 但本地 StopManager 繼續保護

**WP-CC/FS-1 — market_data_client tests 提取**
- `market_data_client/mod.rs` 從 1083→742 行（低於 800 警告線）
- 18 tests 提取至獨立 `tests.rs`，全部通過

**WP-CC/BI-1 — MODULE_NOTE 雙語補全**
- 12 個 Rust 文件補全 MODULE_NOTE（EN+中文）header

**WP-CC/SM-1 — Singleton 合規確認**
- 審計確認無未登記 singleton

**6-01~03 — 策略漸進放權管線**
- 新增 `promotion_pipeline.py`（~640 行）：PromotionGate class
  - 5 階段：LEARNING → PAPER_SHADOW → DEMO_ACTIVE → LIVE_PENDING → LIVE_ACTIVE
  - Paper 畢業門檻：14d + 100 trades + PnL≥0% + DD<10% + Sharpe>0.5
  - Demo 畢業門檻：21d + 200 trades + DD<8% + Sharpe>0.8 + slippage<15bps + reliability>95%
  - LIVE_ACTIVE 必須 operator 顯式審批（APPROVED/REJECTED/EXTEND）
  - Thread-safe（Lock）+ audit callback + DB 序列化 round-trip
- 3 API endpoints 加入 `governance_routes.py`：
  - `GET /promotion-pipeline/status` — 查詢管線狀態
  - `POST /promotion-pipeline/promote` — 晉升（含畢業門檻預檢）
  - `POST /promotion-pipeline/operator-decision` — Operator 審批
- 27 tests（5 classes：StateMachine/GraduationGates/LiveApproval/Audit/Serialization）

**E2 審查修復**
- P1：`register_strategy()` 返回 copy 而非 mutable ref
- P1：JSON API endpoints 不對 lookup key 做 html.escape（避免 key 不匹配）
- P1：lazy singleton 加 threading.Lock 修復 TOCTOU race
- P2：capital_pct/max_leverage 加類型+範圍驗證

**測試基準線**：Rust engine lib 879 / Python 2787 passed / 0 fail

### W19 安全補強：G-3 IPC 認證 + OC-3/6-RC-6 告警（2026-04-10 · commit W19）

**G-3 / SEC-08 — IPC HMAC-SHA256 認證**
- Rust `ipc_server.rs`：新增 `verify_ipc_token()`（常數時間 `mac.verify_slice`）+ `handle_connection()` auth 區塊：`OPENCLAW_IPC_SECRET` 存在時第一條消息必須是 `__auth` JSON-RPC；時間戳 ±30s 防重放；所有失敗路徑立即斷開
- Python `ipc_client.py`：新增 `_authenticate()` 方法；`import hmac as _hmac_lib` + `hashlib`；`_try_connect()` 在 `_connected=True` 後調用；auth 失敗 fail-closed（關閉連接 + return False）；無 env var 時跳過（向後兼容）
- Python `ipc_client.py`：新增 `get_risk_runtime_status()` 方法（OC-3 輪詢基礎）

**G-5 — API Rate Limiting 全局覆蓋驗證**
- 確認 `main_legacy.py:304-307` `default_limits=[120/min]` + `SlowAPIMiddleware` 已覆蓋全部 214 路由
- Gap 審計誤判（PA 以為只有 3 個路由有 decorator，實際 default_limits 已全局生效）
- Login 端點保留更嚴格的 5/min decorator

**OC-3 + 6-RC-6 — Reconciler governor tier 分級告警**
- `paper_trading_wiring.py`：新增 `reconciler_alert_monitor()` 協程 + 加入 `__all__`
  - 每 30s 輪詢 `get_risk_runtime_status` IPC
  - CIRCUIT_BREAKER / MANUAL_REVIEW → 🛑 P0 alert
  - CAUTIOUS / REDUCED / DEFENSIVE → ⚠️ P1 alert
  - NORMAL 恢復 → ✅ INFO
  - 使用 `asyncio.to_thread` 包裹同步 `ALERT_ROUTER.alert_system`（避免阻塞事件循環）
  - `prev_tier=None` 初始化跳過啟動虛假告警
- `main.py`：startup handler 以 `asyncio.create_task()` 啟動監控（fail-open，不阻斷啟動）

**測試結果**：Rust 879 passed · Python 2760 passed (0 fail · 5 skipped)

### 全系統審計 + Gap 計劃（2026-04-10 · PM/PA/FA/CC）

**背景**：PM/PA/FA/CC 四角色對 Rust engine + Python 控制層 + ML pipeline 進行嚴格完成度審計，發現文檔宣稱「~100%」但實際完成度 72-75%。

**關鍵發現**：
- H1-H5 AI 治理層 5 個 agent handler 全為 stub（ai_service.py），AI 判決層無效
- FundingArb.on_tick() 永遠返回 vec![]（第 5 個策略不產生信號）
- API 203 個路由無全局 Rate Limiting
- HMAC dead import、Calibration.py 骨架
- 以上均未出現在原 TODO.md

**動作**：10 個 gap（G-1~G-10）全部入 TODO.md Gap 索引，排入 W19~W23；CLAUDE.md §十更新排期；最早 Live 日期修正為 W23 末（2026-05-16）。

---

### DB Fresh-Start Reset（2026-04-10 · commit 3acb9cc）

**背景**：開發過程中積累了大量噪音數據（52.9M signals、18.3M decision_context_snapshots、3.6K fills 等），PH5-VERIFY-1 觀察期需要乾淨數據基準。

**執行**：`helper_scripts/db/fresh_start_reset.py --execute` — 71,298,138 行開發噪音清除，耗時 <2s（TimescaleDB chunk drop）。

**保留**：所有 `market.*` 表（klines 44K / market_tickers 1.4M / ob_snapshots / funding_rates 等）完整保留。

**影響**：
- PH5-VERIFY-1 觀察期從 2026-04-10 重新起算（原計劃 2026-04-11 `--days 3` → 改為 `--days 2`）
- JS-1 滾動重跑排程：2026-04-11 `--days 2` → 04-12 `--days 3` → 04-17 `--days 7` → 每週滾動

---

### Python OMS 刪除 + Rust DB 訂單/裁決寫入（2026-04-10 · commit 4cab87c）

**Track A — Rust DB writers**: `TradingMsg::Order` + `OrderStateChange` + `RiskVerdict` 三 variant 加入 `database/mod.rs`；`trading_writer.rs` 新增 `flush_orders` / `flush_order_state_changes` / `flush_verdicts`（INSERT 至 `trading.orders` + `order_state_changes` + `risk_verdicts`）；`event_consumer/mod.rs` 在 pending_reg / Fill / Cancelled / Rejected 四點 emit DB 寫入；`tick_pipeline.rs` 三點 emit RiskVerdict。

**Track B — Python OMS 刪除**: `oms_state_machine.py`（693行）+ `test_oms_state_machine.py`（449行）刪除；`governance_hub.py` 移除 `set_oms_sm` / `get_oms_orders` / `_handle_oms_reconciliation` + OMS reconciliation trigger；`governance_routes.py` GET /oms/orders → stub 空列表 + 遷移說明；`paper_trading_wiring.py` 移除 OMS TTL auto-cancel；`conftest.py` 移除 OMS fixtures + helper；tests 更新。

**結果**: Rust 872 lib tests ✅ / Python 2372 passed / 1 pre-existing fail。

---

### Phase 6: 6-RC-7 e2e 集成測試 + 6-RC-8 Live Blocker 解除（2026-04-10）

**6-RC-7**: `tests/reconciler_e2e.rs` — 7 個端到端場景：(1) MajorDrift→Cautious full chain (2) persistent 3 cycles→Defensive (3) burst 5+→CB+CloseAll (4) recovery Cautious→Normal (clean cycles + wall-clock) (5) CB de-escalation blocked (6) REST failure streak→Cautious (7) floor rule prevents over-recovery。`event_consumer::handlers` 模組升為 pub 供集成測試驅動。`TickPipeline::trading_mode` 升為 `pub(crate)` 修復跨模組訪問。

**6-RC-8**: Reconciler 自動降級功能完整（6-RC-1~5,7,9,10），不再構成 Live 隱含阻塞。唯一排除項：6-RC-6（多通道告警，阻塞 OC-3）。

---

### DEAD-PY-2 大型 Python 死代碼清除（2026-04-10 · commit TBD）

~4500 行 Python 死代碼刪除。Python 層完全無交易邏輯。

**Phase A — PipelineBridge 全刪**：`bridge_core.py`（807）/ `bridge_agents.py`（928）/ `bridge_stats.py`（825）/ `pipeline_bridge.py`（807）全刪。`strategy_wiring.py` 移除全部 Bridge wiring；`paper_trading_wiring.py` / `governance_routes.py` / `main.py` 清理所有引用。`main.py` 移除 SymbolCategoryRegistry→PipelineBridge 背景初始化塊。

**Phase B — Python 策略類全刪**：`strategies/{ma_crossover,bollinger_reversion,funding_rate_arb,grid_trading,bb_breakout}.py` 全刪。`strategy_auto_deployer._deploy_strategy()` stubbed to no-op（DEPRECATED R-07）。

**Phase C — ProtectiveOrderManager 全刪**：`protective_order_manager.py` 刪除。`paper_trading_wiring.py` `PROTECTIVE_ORDER_MANAGER = None`。

**Phase D — BybitDemoConnector 瘦身**：763→~95 行。刪除全部交易方法（BybitDemoConnector 類本身），僅保留 `round_qty_for_exchange()` + `round_price_for_exchange()` 兩個純工具函數。

**Phase E — Tests 清理**：11 個死 test 文件完全刪除（~7000 行）；10+ 個 test 文件外科手術刪除 dead class/method；startup integrity + strategy routes 更新適配 DEAD-PY-2。

**E4**：872 Rust lib + 2427 Python passed（1 pre-existing fail）。

### Phase 6: Reconciler Auto-Contraction（自動降級）（2026-04-10）

**6-RC-1~5,9,10 complete** — Position Reconciler 從 AUDIT-ONLY 升級為自動動作層：漂移→風控收緊（降級）→引擎行為限制→漂移消失→自動恢復。

**risk_gov.rs**：+`RiskInitiator::Reconciler` + `RiskEvent::ReconcilerDrift/RestFailure/Recovery` + `reconciler_escalate_to()`/`reconciler_de_escalate_to()` 便捷方法 + transition rules（CB/MR 不可自動恢復）。+5 tests。

**position_reconciler.rs**：`ReconcilerState`（drift_streak/clean_cycles/cooldowns/pre_escalation_level） + `ReconcilerAction` enum（Escalate/DeEscalate/CloseAll） + `evaluate_actions()` pure function：≥5 burst→CB+CloseAll / persistent ≥3 cycles→Defensive / single→Cautious + per-symbol 30min + global 5min cooldown + hybrid recovery（clean cycles + wall-clock）。`filter_dust()` 6-RC-5（1.5×minQty）。Staleness 6-RC-9（>10min→reseed）。REST failure 6-RC-10（≥10→Cautious）。+17 tests。

**tick_pipeline.rs**：+`ReconcilerEscalate`/`ReconcilerDeEscalate` PaperSessionCommand variants。

**handlers.rs**：+2 command handlers（parse tier → reconciler_escalate/de_escalate → force snapshot）。

**main.rs**：`Arc<AtomicU8>` shared_risk_level 接線：main.rs 創建 → event_consumer 每次 handle_paper_command 後寫入 → reconciler 閉包讀取。

**event_consumer/types.rs + mod.rs**：`shared_risk_level: Option<Arc<AtomicU8>>` 加入 EventConsumerDeps。

**tests**：872 engine lib + 365 core = 1237 all pass（+27 new: 17 reconciler + 5 risk_gov + 5 handler）。

**觸發矩陣**：MinorDrift→no action / MajorDrift/Orphan/Ghost/SideFlip→Cautious / persistent ≥3→Defensive / burst ≥5→CB+CloseAll / REST fail ≥10→Cautious。

**恢復矩陣**：Cautious→Normal: 30 cycles+15min / Reduced→Cautious: 20+10min / Defensive→Reduced: 20+10min / CB/MR: operator only。MinorDrift 不重設 clean cycle。Floor rule：不低於 pre_escalation_level。

**排除**：6-RC-6（多通道告警，阻塞 OC-3）、6-RC-7（e2e 整合測試）、6-RC-8（live blocker）。

---

### Signal Diamond Phase 3+4 Fix Round — Mode Switch + IPC Commands（2026-04-10）

**P0: `set_trading_mode()` state swap** — 替換原 2 行 setter 為完整雙向 `std::mem::swap` 實現：`sync_direct_to_mode_state(old)` 保存舊模式 → `load_mode_state_to_direct(new)` 載入新模式。切換 paper↔demo↔live 時保留各自的 PaperState/IntentProcessor/GovernanceCore/consecutive_losses/session_halted/pending_close。同模式切換為 no-op。新模式自動 `add_mode()` 以當前餘額初始化。

**P2: PaperSessionCommand 擴展** — 新增 `AddMode { mode, balance, response_tx }` 和 `SwitchMode { mode, response_tx }` variants。`event_consumer/handlers.rs` 完整處理：pipeline 操作 + force snapshot write + oneshot response。`ipc_server.rs` 註冊 `add_engine_mode` / `switch_engine_mode` RPC（嚴格 enum match，3s timeout）。

**P3: Python IPC 層** — `ipc_client.py` `get_paper_state(mode=)` 傳遞 `{"engine": mode}` 參數；新增 `get_mode_snapshot()` / `get_active_modes()`。`ipc_state_reader.py` mode-aware lookup + `_MODE_ALIASES` fallback（"paper"↔"paper_only"）。`live_session_routes.py` 所有 IPC call 帶 `{"engine": "live"}`。

**P1 架構決策** — 同時多模式 on_tick 需 per-mode 策略實例（grid/bb_breakout 有內部狀態如 net_inventory）。當前架構支持模式**切換**（state preservation），真正同時執行為 Phase 5+ 工作。

**ModeStateSnapshot** — `mode_state.rs` 新增 IPC 序列化結構體。`PipelineSnapshot.mode_snapshots: HashMap<String, ModeStateSnapshot>` 對主模式讀 direct fields、次模式讀 mode_states。`TradingMode` 加 `Hash` derive。

**測試** — +5 新測試（preserve state / same-mode noop / add_mode+snapshot / pipeline_snapshot / consecutive_losses roundtrip）。**E2 PASS WITH WARNINGS**（僅 file size pre-existing）。**E4: 850 Rust lib / 3 integration / 2692 Python pass, 1 pre-existing fail**。

### SM-1 live 授權統一 + Governance 修復（2026-04-10 · commits 4815386 / 435e613）

**問題 1 — max_position_usd 硬編碼**：`governance_hub.grant_paper_authorization()` scope 中 `max_position_usd: 10000` 為字面量。修復：新增 `max_position_usd: float = 10_000.0` 參數；`post_session_reauth` 改 async，IPC 讀取 Rust `RiskConfig.limits.max_order_notional_usdt`，>0 時覆蓋預設值。

**問題 2 — SM-1 live 授權從未 ACTIVE**：`_submit_live_governance_request()` 只走到 PENDING_APPROVAL，Operator role + live_reserved 雙重門控從未完成 SM-1 批准。修復：(a) `_submit_live_governance_request()` 在 `submit_for_approval` 後立即 `approve()`，使 live auth DRAFT→PENDING→ACTIVE，並 invalidate HUB cache；(b) 新增 `_revoke_live_governance_auth()` — 撤銷所有 mode=live 的 SM-1 auth（ACTIVE/RESTRICTED/PENDING/DRAFT → REVOKED）；(c) `grant_execution_authority()` 同步調用 `_submit_live_governance_request()`；(d) `revoke_execution_authority()` + `post_live_session_stop()` 同步調用 `_revoke_live_governance_auth()`；(e) `governance_hub.get_status()` 多授權並存時優先顯示 `mode=live` 授權。

**效果**：live session start → 治理中心顯示 `mode: live / execution: live_submit / approved_by: <actor>`；stop/revoke → 恢復 `paper only`（若 paper auth 仍有效）；drawdown halt → FROZEN（不變）。2676 Python tests pass。

### Live/Demo GUI 平倉按鈕 + Sidebar mode 修復（2026-04-10 · commits c370cd1 / bfc3cea / 81a0acb）

**Sidebar 修復**：`console.html refreshSidebar()` 改用 `/api/v1/live/session/status` 替代 `governance/status`，正確讀取 `trading_mode` / `execution_authority` / `session.session_state`；live 且 granted 時顯示紫色 mode + `auth: granted`，否則顯示 `Live_Ready`。

**後端新端點**：(a) `POST /api/v1/live/positions/{symbol}/close` — IPC `close_position`，Operator role，session 繼續；(b) `POST /api/v1/live/close-all-positions` — IPC `close_all_positions`，session 繼續；(c) `POST /api/v1/strategy/demo/positions/{symbol}/close` — PyO3 `get_positions` 查 qty/side → `place_order reduce_only=True`；(d) `POST /api/v1/strategy/demo/close-all-positions` — `_close_all_demo_positions()`。

**前端**：live/demo 持倉表各行末尾加「平倉」按鈕（confirm dialog + `ocPost`）；Positions section header 加「全部平倉」按鈕；移除 control bar 原有重複「關閉所有倉位」按鈕；paper tab 同步加「全部平倉」；`_normalize_execution()` 處理 Rust snake_case→Bybit camelCase（execQty/execPrice/execFee）。2280 Python tests pass。

### Signal Diamond Multi-Engine Data Separation — Phase 1-4 Complete（2026-04-10）

**Phase 1: V015 Migration** — `sql/migrations/V015__engine_mode_separation.sql` adds `engine_mode TEXT NOT NULL DEFAULT 'paper'` to 8 trading tables + nullable on `agent.ai_invocations`. Indexes `(engine_mode, ts DESC)`. `trading.signals` untouched (shared). DEPRECATED comments on `is_paper` columns.

**Phase 2a: Rust DB Writers** — `TradingMsg::Intent/Fill/PositionSnapshot` + `DecisionContextMsg` gain `engine_mode: String`. `trading_writer.rs` flush functions write `engine_mode` column; `is_paper` derived as `engine_mode != "live"` (backward-compat Grafana). `context_writer.rs` flush adds `$26 = engine_mode`. `TradingMode::db_mode()` canonical mapping: PaperOnly→"paper", Demo→"demo", Live→"live".

**Phase 3: ModeState Extraction** — New `mode_state.rs`: `ModeState` struct (PaperState + IntentProcessor + GovernanceCore + risk_store + ring buffers + consecutive_losses + session/pause flags + pending_close + exchange_seq) + `ModeStateSnapshot` for IPC. `TickPipeline` gains `mode_states: HashMap<TradingMode, ModeState>` + `active_modes: Vec<TradingMode>`. Primary mode bridge: `mode_snapshot()` reads from direct fields for primary mode, ModeState for secondary. `PipelineSnapshot.mode_snapshots` added. `TradingMode` gets `Hash` derive.

**Phase 4: IPC + Python** — Rust `ipc_server.rs`: `get_paper_state` accepts optional `engine` param (default "paper"); new `get_mode_snapshot` and `get_active_modes` methods. Python `ipc_state_reader.py`: `get_paper_state(mode=)` with `mode_snapshots` lookup + alias handling; new `get_mode_snapshot()`, `get_active_modes()`, mode-aware `get_recent_intents/fills()`. `live_session_routes.py`: all IPC calls pass `{"engine": "live"}`.

845 Rust lib tests pass. 2692 Python tests pass (1 pre-existing fail).

### Live-Demo 槽位 + Live/Paper Metrics 修復 + DB Signal Diamond 規劃（2026-04-10 · commit 25b5d73）

**`settings_routes.py`**：新增 `live_demo` 虛擬槽位（validate via demo server → 寫入 live path；operator 可用 Demo 帳號完整測試 live 路徑，換 key 時零代碼改動）。**`tab-settings.html`**：3 API key 卡片（Demo / Live-Demo / Live）+ peek 遮罩按鈕 + dialog overlay CSS 修復 + 槽位上下文警示。**`live_session_routes.py`**：新增 `GET /api/v1/live/metrics` 端點。**`paper_trading_routes.py`**：`/metrics` 端點修復（呼叫 `compute_full_metrics()`，返回完整 trade_metrics / drawdown_metrics / holding_period_metrics / sharpe_ratio，修復所有指標顯示 "--"）。**`tab-live.html`**：Performance Metrics 區塊（10 個指標卡，30s 刷新）。**`DB_TODO.md`**（新文件）：Signal Diamond 多引擎數據隔離規劃（5 階段實施）。840 Rust lib tests pass。

### Live 縮倉監控 + OPENCLAW_ALLOW_MAINNET 鎖移除（2026-04-10 · commit 25b5d73）

**Rust `bybit_rest_client.rs`**：移除 `OPENCLAW_ALLOW_MAINNET=1` env var guard（9 行），保留主網 warn 日誌；更新 `config/mod.rs` TradingMode::Live docstring + `main.rs` 注釋。840 Rust lib tests pass。

**`live_session_routes.py`**：新增 `_live_contraction_monitor()` async 後台 task — 每 5 分鐘輪詢引擎 `peak_balance + bybit_sync_balance/balance`，計算 session 回撤；`CONTRACTION_WARN_PCT=5.0%` → 警告日誌；`CONTRACTION_HALT_PCT=15.0%` → 撤銷 `execution_authority` + `close_all_positions` IPC + `_freeze_live_governance_auth()`；新增 `_freeze_live_governance_auth()` 凍結 GovernanceHub 中 mode=live 授權（審計留痕）；`post_live_session_start` 啟動 monitor task + 初始化 `_live_contraction_state="normal"`；`post_live_session_stop` 取消 task + 重置狀態；`post_live_session_resume` 重啟 monitor task；`get_live_session_status` 加入 `contraction{}` 字段（state/warn_pct/halt_pct/drawdown_pct/peak_balance/current_balance）。

**`tab-live.html`**：控制欄新增 `#live-contraction-badge`：normal 時隱藏；warned 時顯示黃色警告 + 回撤 %；halted 時顯示紅色 + 禁用 Start 按鈕。

### Gov-P1 + Live_Ready 全阻隔移除（2026-04-10 · commit 045e79c）

**`live_session_routes.py`**：`post_live_session_start` 自動授予 `execution_authority = "granted"`（雙重門控 Operator 角色 + live_reserved 已足夠，不再需要額外 grant 步驟）；`post_live_session_stop` 重置 `_EXECUTION_AUTHORITY_OVERRIDE = None`（fail-closed）；`post_live_session_resume` 移除舊 execution_authority 硬鎖，改為 global_mode 二次確認 + 重授；新增 `_submit_live_governance_request()` — live session start 時向 GovernanceHub 提交 PENDING 授權申請（非阻塞，審計留痕，Operator 可在治理頁確認）。

**`tab-live.html`**：`checkLiveEngineStatus()` detail 行邏輯修改 — active 時顯示 `mode | authority`，idle 時只顯示 `mode`（消除 `authority: not_granted` 噪音）。

**`CLAUDE.md`**：§四 `execution_authority = "auto_granted_on_start"` + 硬錯誤清單更新；§三 Runtime 狀態更新為 Live_Ready ✅ 全阻隔已移除；§十一 一句話更新。

**测试**：840 Rust lib pass · 2280 Python pass · 1 pre-existing fail 不變。

### Live GUI Phase 5 — 紫色主題 + 擴展儀表板 + Global Mode Gate（2026-04-10 · commit c392220）

**tab-live.html**：CSS 全面紅→紫（warn-bar/control-bar/accent borders → rgba(168,85,247,..)）；Account Balance 卡片組（total equity / available / wallet balance / margin used = equity - available）；PnL Overview 卡片組（unrealized large + realized from cumRealisedPnl sum + net PnL）；持倉表新增 Leverage 列；成交記錄折疊區（懶加載 `/api/v1/live/fills`，展開時觸發）；active badge `oc-chip-bad` → `oc-chip-live`；緊急停止按鈕保持紅色。

**tab-system.html**：`live_reserved` 按鈕邊框/圖標 🔴→🟣 + 紫色；`updateModeBtns` chip `oc-chip-bad`→`oc-chip-live`；MODE_CONFIRM warn-box 紅→紫；loadOverview metric class `red`→`purple`（新增 `.purple { color: #a855f7 }` CSS class）；模式升级路径顏色紅→紫。

**live_session_routes.py**：`_get_global_mode_state()` 讀 STORE `global_runtime.derived.global_mode_state`；`post_live_session_start` 新增 409 gate（global mode 必須含 'live'）；`GET /api/v1/live/fills` 新端點（PyO3 `get_executions` + fallback）。

**common.js**：`oc-chip-live` 紫色 chip CSS class（rgba(168,85,247,..)）。

**console.html**：live mode mc-val 顏色改為 `#a855f7` inline style；BUILD_TS → `20260410.live-ui-v2`。

### Live GUI Phase 4 — 授權 gate + PyO3 真實數據 + _ipc_command 修復（2026-04-10 · commit af392c2）

**live_session_routes.py**：`_EXECUTION_AUTHORITY_OVERRIDE` 記憶體覆蓋（重啟清空 fail-closed）；`_get_execution_authority()` 先查 override 再走 governance；`_ipc_command()` 3 bug 修復（錯誤 import / 未 connect / 未 disconnect）；`_get_rust_client_safe()` helper；`POST /api/v1/live/execution-authority/grant` + `/revoke`（operator-only）；live session start 接受 `demo` mode（demo key 測試）；`GET /api/v1/live/balance|positions|orders` 改為 PyO3 BybitClient 優先（真實帳戶數據），IPC 降級。

**tab-live.html**：lock screen 加「Grant Execution Authority」按鈕；dashboard 加「撤銷授權」按鈕；`grantLiveAuthority()` / `revokeLiveAuthority()` JS；balance 解析支援 PyO3 snake_case + Bybit camelCase 雙格式 + unrealized PnL；positions 移除 `p.position` 嵌套（Bybit 扁平格式）；orders 使用真實 Bybit 欄位（orderId/price/orderType/orderStatus）。

E4：840 Rust + 2280 Python passed，1 pre-existing fail。

### Live_Ready 狀態切換 + live 端點上線（2026-04-10 · commit 09a5d02）

CLAUDE.md §四 hard limits 更新：移除 `system_mode=demo_only` / `execution_state=disabled` 硬限制。新 Live 技術門控：OPENCLAW_ALLOW_MAINNET=1 + live API keys + execution_authority=granted（三條件全滿足才真實接入主網）。

新增 3 個實盤端點（`live_session_routes.py`）：`GET /api/v1/live/balance` / `/live/positions` / `/live/orders`，全部走 IPC `get_paper_state`，引擎不可用時優雅降級。

`tab-live.html`：`loadDashboardData()` 呼叫 live 端點（非 demo）；訂單表完整接線（原 LIVE-P1-3 stub）；phase badge 更新為 "✅ Live_Ready"。

`main.rs` 啟動 banner：`demo_only | Execution: disabled` → `Live_Ready | Execution: operator-gated`。

---

### L3 嚴格審計 + 2 bug 修復（2026-04-10 · commit ed26346）

4 路並行 agent 審計 LIVE-P0/P1/P2 所有層次：Rust ipc_server/main、Python risk_routes/live_session、GUI tab-risk/live/settings、LIVE-P1 Rust TradingMode。

**CRITICAL: live_session_routes._ipc_command() 三重斷線**（Python C-1/C-2/C-3）— 原碼 import `get_ipc_client`（不存在）、從未 connect()、從未 disconnect()；所有 live session 端點靜默返回 HTTP 503。修復：EngineIPCClient + connect/call/finally disconnect（同 paper_trading_routes 模式）。

**C2: in-tp-enabled checkbox dirty-tracking 缺失**（GUI）— checkbox 用 change 事件但不在 _RISK_INPUT_IDS forEach 裡；修復：加獨立 change 監聽器。

已驗證乾淨：Rust TradingMode match 窮舉、OPENCLAW_ALLOW_MAINNET 硬鎖、key slot routing、per-engine whitelist、p1_risk_pct 轉換。已確認設計決策（非 bug）：TOML 無磁盤 hot-reload、risk_store 啟動鎖定、tab-live stub 前置條件、execution_authority Python-only guard。

E4：840 Rust lib / 2280 Python + 1 pre-existing fail — 無回歸。

---

### LIVE-P2-1/P2-2/P2-3 per-engine RiskConfig separation（2026-04-10 · commit 006d905）

**LIVE-P2-1 Rust PerEngineRiskStores**:
- New `PerEngineRiskStores` struct bundles 3 `Arc<ConfigStore<RiskConfig>>` (paper/demo/live); replaces single Optional field
- `IpcServer.risk_stores: Option<PerEngineRiskStores>`; `set_config_stores()` takes full struct
- IPC `get_risk_config`/`patch_risk_config` accept optional `engine` param, route to correct store (default paper fail-safe)
- `main.rs`: `load_unified_configs()` loads 3 TOML files with env var overrides; legacy fallback `risk_config.toml` → paper if `risk_config_paper.toml` absent
- `async_main()` selects correct store by `TradingMode` for `EventConsumerDeps.risk_store`
- New TOML: `risk_config_paper.toml`, `risk_config_demo.toml` (same as paper); `risk_config_live.toml` (conservative: leverage 10x, position 5%, drawdown 5%, daily_loss 3%)

**LIVE-P2-2 GUI per-engine tab**:
- `tab-risk.html`: engine selector card (Paper/Demo/Live); live warning banner; confirmation modal before live saves
- `_selectedRiskEngine` state; `loadRiskConfigForEngine()` calls new per-engine endpoint; `_engineSaveUrl()` routes saves; `_wrapLiveSave()` intercepts live saves

**Python per-engine endpoints** (`risk_routes.py`):
- `GET /api/v1/paper/risk/config/engine/{engine}` — direct IPC, bypasses RiskViewClient version tracking
- `POST /api/v1/paper/risk/config/engine/{engine}/global` — direct IPC patch with engine routing
- `_ALLOWED_ENGINES` whitelist prevents path injection

**E2+E4**: zero review issues; 840 Rust lib tests / 2280 Python + 1 pre-existing fail pass.

---

### SEC-05 innerHTML XSS + WP-F/AH-06 risk-tab dirty-tracking（2026-04-10 · commits 19b40dc + b7b7651）

**SEC-05 innerHTML XSS remediation** across GUI:
- `app.js`: `safeText()` now delegates to `ocEsc()` (covers ~20+ call sites at once); 15+ individual `ocEsc()` wraps for paper positions/orders/fills, market feed, learning feed, cost breakdown, risk envelope
- `app.js` supplement (b7b7651): 4 badge/label function fallbacks escaped — `confidenceBadge`, `statusBadge`, `reviewStatusBadge`, `reviewTypeLabel`
- `cards/linucb_card.html`: `ocEsc()` on regime names, arm_id, shadow champion/challenger/decision
- `tab-ai.html`: `ocEsc()` on Kelly strategy keys and tier labels
- Remaining files (tab-governance, tab-settings, tab-system, tab-live, console) audited — already properly escaped or use hardcoded data only

**WP-F/AH-06 risk-tab form overwrite fix**:
- `tab-risk.html`: `_riskFormDirty` flag set on any input event across 16 risk form fields
- `loadRiskConfig()` skips populating inputs when dirty flag is true
- Flag cleared after successful save in all 3 save functions
- Replaces inadequate `document.activeElement` guard that only protected focused element

### A2 NewsPipeline Scheduler + DEAD-PY-1 Complete + 1C-4 Close（2026-04-10）

**A2 NewsPipeline 60s scheduler** wired into `main.rs`:
- 3 providers: CryptoPanic (free tier, 28min self-throttle) + CoinTelegraph RSS + Google News RSS
- 4-09 triple-route NewsRouter: Guardian halt check + regime buffer + learning context sink
- Gated by `LearningConfig.switches.news_pipeline_enabled` (hot-reloadable via ConfigStore)
- Follows existing fee_rate/instrument refresh tokio::spawn pattern with cancel token
- ~95 lines added to `main.rs`

**DEAD-PY-1 whitelist UI removal** (WP-CLEANUP-WHITELIST-UI):
- `tab-governance.html`: removed HTML card + modal + CSS + JS vars/functions + init + explainers (−220 lines)
- `governance.js`: removed 3 dead API wrapper functions (−19 lines)
- All whitelist references eliminated; backend already returns HTTP 410 Gone

**1C-4 final verification**: E2 code review + E4 regression (838 Rust lib / 2692 Python passed / 1 pre-existing fail) + doc sync

### LIVE-P0-1/P0-2/P0-3 — API key mgmt + live page rewrite（2026-04-10 · commit c680ffd）

- `settings_routes.py` (new): GET/POST /api/v1/settings/api-key/{slot}  
  Slot whitelist → HMAC validation → write + chmod 600 → masked hint only  
- `main.py`: registered settings_router  
- `tab-settings.html`: API key management card for demo/live slots  
- `tab-live.html`: full rewrite — dynamic prereq checklist (10 checks, live API queries) + dashboard framework (lock overlay / unlocked with PnL metrics / positions table / emergency stop)  
- Tests: 2692 passed / 1 pre-existing fail (unchanged)

### ML Pipeline Audit Gap Fixes（2026-04-10）

Cold audit of all ML_TODO completed items found 3 real issues + 4 pre-existing test failures:

**Fixes**:
1. `cpcv_validator.py` — `model_name`/`model_version` now parameterized through `validate_cpcv()` (was hardcoded `"lightgbm_scorer"`/`"v1"`)
2. `bybit_demo_sync.py` — `_get_conn()` now prefers db_pool, fallback to direct `psycopg2.connect()`; `_release_conn()` returns to pool or closes
3. `test_phase4_routes.py` — 4 "no PG" tests now mock `db_pool.get_conn` (were broken by previous db_pool migration but not caught)
4. `test_bybit_demo_sync.py` — 2 tests updated to assert `_release_conn` instead of `conn.close`
5. ML_TODO.md archived to `docs/worklogs/2026-04-10--ml_pipeline_remediation_complete.md`, removed from root

**Test baselines**: control_api 2678 passed / 1 pre-existing fail · ml_training 135 passed / 6 skipped

---

### ML Pipeline Remediation — S0-S3+S5（2026-04-10）

基於 2026-04-09 DB R/W + ML Pipeline 全面審計完成大規模修復。

**Rust cost_gate 統一（S1）**：
- `intent_processor.rs`：5-tier slippage lookup、ATR% 正規化、win_rate 加權門檻（`fee_bps / max(0.3, wr) * 1.3`）
- `edge_estimates.rs`：`CellEstimate` struct（win_rate, n_trades, std_bps）、`get_cell()` + `load_from_str()`
- 838 lib tests pass（基準 835→838，+3 new: slippage_tier, js_win_rate, atr_pct）

**ML 推理管線（S2）**：
- `parquet_etl.py`：加時間窗口過濾 `WHERE updated_ts_ms >= start_epoch_ms`
- `label_generator.py`：修復 zero-ATR floor（`np.quantile` on empty array）+ 2 test fixes
- FeatureCollector 已接線確認（審計報告過時）

**參數優化管線（S3）**：
- `optuna_optimizer.py`：`_persist_suggestion()` → `learning.ml_parameter_suggestions`（V004 DDL 已上線）
- `cpcv_validator.py`：`_persist_cpcv_result()` → `learning.cpcv_results`
- Thompson Sampling：確認為 (A) offline 工具，`bayesian_posteriors` UPSERT 已存在

**DB 基礎設施（S5）**：
- `db_pool.py`（NEW）：`ThreadedConnectionPool`（min=2, max=10），singleton + env var 可配
- `grafana_data_writer.py` + `strategy_read_routes.py` + `phase4_routes.py`：全部委託到 db_pool
- `strategy_read_routes.py`：DB 失敗返回 HTTP 503（非 200 空數據）
- `/api/v1/health/db` endpoint：連接池統計 + SELECT 1 探測
- 2692 Python tests pass（基準 2678→2692），1 pre-existing fail · 160 ML tests pass（基準 135→160）

---

> **歸檔**：2026-04-08 ~ 04-09 條目已移至 `docs/archive/2026-04-13--changelog_archive_0408_0409.md`。
> 2026-03-30 ~ 04-07 條目見 `docs/archive/2026-04-12--changelog_archive_pre_0408.md`。
