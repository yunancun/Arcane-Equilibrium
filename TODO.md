# 玄衡 TODO — 活躍派工佇列

版本：v56-zh（基於 v56 翻譯與精簡）
日期：2026-05-19
狀態：本檔僅保留 ACTIVE / PENDING / ACTIVE-WATCH 項目；所有歷史 ✅ DONE 詳情已歸檔。

## §-1 v56 緊急狀態 — P0 trading-inert incident（2026-05-19 ~20:00 UTC）

- **事件**：engine PID 1942669（UTC 12:27:11 watchdog respawn）處理 2 次 FILUSDT halt_session emergency close 後（12:27:14 + 12:27:37），進入 **7h43m TRADING-INERT**（0 intents / 0 orders / 0 fills；WS alive、~1k ticks/sec、IPC alive；panel_aggregator channel_len=65+ backpressure）。
- **復原**：operator `restart_all.sh --keep-auth` UTC 20:09:36 → 新 PID 2099215；首筆 fill 在 restart 後 1 分鐘；24 分鐘內 5 fills / 3 symbols，正常交易恢復；Phase 1b verification sample n=13 繼續累積。
- **E2 RCA**（`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-19--engine_watchdog_respawn_loop_and_trading_inert_rca.md`）：
  - 本 bug = `paper_paused=true` sticky from Step 6 `RiskAction::HaltSession`（`step_6_risk_checks.rs:434-461`）**無 TTL auto-clear**；只 4 種 clearer：IPC Resume / Reset / SystemMode::ShadowOnly / restart default init
  - 與先前 `P1-WATCHDOG-STATUS2-RCA` **不同根因**（先前只覆蓋 systemd cosmetic naming `sys.exit(2)`）
  - Watchdog 無「alive but inert」偵測（只看 snapshot freshness；engine 每 30s 寫 status_report 不論是否交易）
  - **Halt 觸發數學不通**：drawdown 10.2% vs TOML 25% threshold — trigger 根因仍 UNRESOLVED（log rotation 失了 UTC 12:27 那一行；可能 IPC patch / loading-order race / 第三條路徑）
- **Operator 決議 2026-05-19 ~20:30 UTC**：
  - Layer A：TTL clear **只清 daily_loss**（rolling）；drawdown 維持 sticky（session safety-critical，operator-only resume）
  - Layer B：Watchdog 業務 heartbeat probe **僅告警**（不自動 restart）
- **PA spec 已派**：`docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md`（~600-1000 LOC，ETA 2-3h）
- **嚴重度 P0**：下次 breach 必復發；demo / live_demo / live 共用同段代碼；Phase 1b verification + 所有 PnL 在 breach 與 operator 發現之間都暴露

任務追蹤條目見 §10 `P0-ENGINE-HALTSESSION-STUCK-FIX`。

---

## §0 v55 / 之前的完工狀態（一段話留底）

v55（2026-05-19 上半段）operator 授權的 4 條並行軌道全收口：

- **#5 watchdog RCA**（DNS/HTTP transport outage 誤判為 `ENGINE_CRASH`）
- **#6 entry-path RCA**（entry-close 0% maker fill 為 path-specific，非全局 PostOnly 壞）
- **#7 tab-live extract**（tab-live.html 2171→543 LOC，內聯 JS 抽到 tab-live.js 1645 LOC）
- **#9 stress fails RCA + #12 E1 R2 fix**（stress_integration.rs 修 2 helper；35/35 PASS）

關鍵 commit：`9bf4fd62` / `c1f47722` / `d927bf7f`。

**QC P2-ENTRY-PATH critical reframe**：原 QA「entry-close vs risk-exit by ID prefix」拆法是結構性人為造成的；兩者都走同一 `execute_position_close()` 路径。真實是 6 maker attempts / 3 fills = 50% Wilson CI [18.8%, 81.2%] 覆蓋 sim 70.8% → 21pp 偏差非 70pp gap。Sample velocity ~0.44 grid_close/hr → 首個可信 verdict 推到 **T+96h~T+120h（2026-05-22~23 UTC）**。

**v55 衍生 backlog**：見 §11.3 / §12（P1-WATCHDOG-EXIT-CODE-CLARIFY / FA-WATCHDOG-3STRIKE-ESCALATION-POLICY / P2-QA-TEMPLATE-CLOSE-MAKER-SPLIT-FIX / P2-SIM-QUEUE-AWARE-ADJUSTMENT / P2-STRESS-BB-BREAKOUT-FALSE-SQUEEZE-COINCIDENTAL-PASS）。

**Governance flag**：`cargo test --lib` 不覆蓋 tests/ integration crate；建議 sign-off SOP 加 `cargo test -p openclaw_engine --release`（no --lib）。

## 翻譯與歸檔說明

- 本次 v56→v56-zh 改寫：全文中文化 + 嚴格清理 ✅ DONE 詳情。
- 已完成項目（含 commit hash、E2/E4 鏈、AMD 修文記錄）轉存到：
  `docs/archive/2026-05-19--todo_v55_translation_archive.md`
- 上次大規模歸檔已在以下文件累積，本次不再重複收納：
  - `docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`
  - `docs/archive/2026-05-15--todo_v24_stale_rows_archive.md`
  - `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`
  - `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`
  - `docs/archive/2026-05-16--stage1_demo_a4c_tombstone_cleanup.md`
  - `docs/archive/2026-05-07--todo_v12_agent_openclaw_replan_archive.md`
  - `docs/archive/2026-05-09--w_audit_verified_closed_archive_v3.md`

維護契約：依 `docs/agents/todo-maintenance.md` 將本檔保持為活躍派工佇列；穩定專案脈絡寫進 `README.md`，agent 操作規則寫進 `CLAUDE.md` / `.codex/MEMORY.md`。

---

## §0.0 PM Freeze — Demo-Only Stage 1 + A4-C Tombstone Guard

**狀態**：ACTIVE PM freeze；AMD-2026-05-15-01 持有 rebase 權威。

- Stage 1 promotion evidence **僅限 Demo**：Stage 0 shadow → Stage 0R replay preflight（`eligible_for_demo_canary=true/false`）→ Stage 1 Demo micro-canary（1 策略 × 1 symbol × 7d）。Stage 0R 不是 Stage 1 PASS。
- Paper 不是 active promotion lane。任何計畫 / 命令 / env / 腳本 / runtime 若設 `OPENCLAW_ENABLE_PAPER=1` 為 promotion 用，**BLOCKED**，除非未來 operator 明示重啟 paper 作非 promotion 診斷用途。
- **A4-C tombstone**：`W-AUDIT-8d` BTC→Alt Lead-Lag 退出 active promotion，封存 no-revive（BTC 1m return + xcorr feature shape）。`panel.btc_lead_lag_panel` / `[57]` 僅保 diagnostic；不得作 Stage 0R 候選或 Stage 1 Demo cohort 來源。
- 未來 A4-C 重啟需：materially new predictive variable + preregistered validation + 全新 strategy×symbol Stage 0R packet 且 `eligible_for_demo_canary=true`。
- 當前 active alpha gates：W-AUDIT-8b Stage 0R 已 tombstoned；W-AUDIT-8a C1 transport proof `PASS_C1_PROOF_CANDIDATE`；W-AUDIT-8c source/test + V095 apply + production `allLiquidation.{symbol}` writer revival 已 DONE。writer revival 不蘊含 liquidation 策略可上線。

---

## §1 Sprint Milestone Banner（業務鏈 63% → 85-89%）

| Sprint | Week | 主題 | E1 capacity | 業務鏈 milestone |
|---|---|---|---|---|
| **N+0** | W1-W2 | FOUNDATION HEAVY：W-AUDIT-9 + 8a Phase A + B 群 + C-A6 + 6 mid-ground | 5 active + 1 stand-by | 63→65% |
| **N+1** | W3-W4 | ALPHA SURFACE PANEL WIRING：8a Phase B+C + 8b Stage 0R + 待未來綠燈 Stage 0R 後 Stage 1 Demo micro-canary 預備 | 4/6 | 65→70%（待 demo canary 證據後重估） |
| **N+2** | W5-W6 | 8a Phase D + Stage 2 demo cohort 14d（限 Stage 1 demo 證據通過後）| 5 active + 1 stand-by | 70→76%（rebase 待定） |
| **N+3** | W7-W8 | 8c（Liquidation）IMPL + 8e（R-2）spec + Stage 3 demo full | 4/6 | 76→80% |
| **N+4** | W9-W10 | 8f（R-3）spec + 8b（Funding Skew）IMPL + 8e IMPL + Track W 收尾 | 4/6 | 80-83% |
| **N+5** | W11-W12 | 8f IMPL + 8g（R-4）spec + **首個 per-alpha-source supervised live** | 5 active + 1 stand-by | **85-89%** |

**Stand-by E1 啟用條件**（operator 拍板 2026-05-09 (a)）：W-AUDIT-9 T3 stage-aware exception path 翻車 / W-AUDIT-8a Phase A byte-diff fail / W-AUDIT-6d mid-ground 與 8a Phase A 撞牆 / 任一 active E1 health incident → stand-by 即時補位。

**Supervised live 機率帶**（FA）：6/15 樂觀 ~30% / 6/30 中位 ~40% / 7/15 悲觀 ~25% / 8/15 極悲觀 ~5%。

---

## §2 架構邊界

- 正式產品：`玄衡 · Arcane Equilibrium`。
- 交易所目標僅 Bybit。
- Rust `openclaw_engine` 是交易 / 風控 / 策略 config / 執行的權威。
- Python/FastAPI 是 control plane / bridge / GUI 後端 / replay+orchestration surface / 本地 5-Agent runtime host。不是交易事實層。
- 標準 GUI = FastAPI console `trade-core:8000/console`（OpenClaw Control Console）。
- 外部 OpenClaw Gateway 僅做通訊 / mobile / supervisor / proposal relay。不是交易 conductor，不是本地 5-Agent runtime，不是第二 GUI。
- 本地 Scout / Strategist / Guardian / Analyst / Executor 留在 TradeBot 內。Cloud L2 呼叫須走一次 supervisor escalation packet + 顯式 budget/model config + durable `agent.ai_invocations` ledger reservation。
- Scanner 是 always-on 基礎設施（市場脈絡 / active-universe attribution / route fitness / opportunity evidence / legacy would-block audit）。不是交易權威，無法 hard-gate opens / closes / live auth / order dispatch。
- `MessageBus` = legacy/advisory trace。權威 agent promotion 須 typed lineage：StrategySignal → StrategistDecision → GuardianVerdict → ExecutionPlan → Decision Lease / idempotency → ExecutionReport。
- Replay 是 advisory / diagnostic。可加速 preflight；不能取代 runtime lineage 或授權 live promotion。
- **Graduated Canary rebase**（AMD-2026-05-15-01 取代 AMD-2026-05-09-03 Stage 1 paper 語意）：alpha-bearing 走 Stage 0 shadow → Stage 0R Replay Preflight（`eligible_for_demo_canary=true/false`，非 Stage 1 PASS）→ Stage 1 Demo micro-canary（1 策略 × 1 symbol × `Environment::Demo` × 7d）→ Stage 2 demo extended ×14d → Stage 3 demo full ×21d → Stage 4 LIVE_PENDING。DOC-08 §12 9 條安全不變量 / SM-04 ladder / Live boundary 5-gate / §二 16 原則硬不變式 4 範圍**仍強制 binary fail-closed**，不被 graduated canary 觸碰。

---

## §3 當前活躍狀態

- W-C MAG-082 Stage 2 **WINDOW_PASS 2026-05-11** 與 W-D MAG-083/MAG-084 **DONE 2026-05-11**：已關閉；proposal / mobile / Stage 3+ / true-live gates 仍另立，被 edge/LG/ops 前置卡。
- A4-C BTC→Alt Lead-Lag active-promotion marker 移除：Step 5b 與 RCA 封存 **GATE-RED / no-revive**；`panel.btc_lead_lag_panel` 留 diagnostic-only。OI-confirmed 5m packet 僅是 replay spec，不改變 eligibility。
- `[55]` 已被 `P1-HEALTHCHECK-55-INVARIANT` source-cleared；`[67]` 經 feature baseline apply 後恢復 PASS；`[4]` phys lock 與 `[Xb]` triangulation 在 `7108035d` 之後 PASS。
- V079 / `learning.strategy_trial_ledger` runtime 已在 `trade-core` 應用（migrations 已到 V090）；觀察到 16,212 ledger rows。舊「V079 未 apply / engine 仍 5/8 binary」敘述已歸檔。
- **業務根因**：5 textbook 策略仍欠持續正 net edge。`P0-EDGE-1`、`P0-LG-1/2/3`、`P0-OPS-1..4`、Alpha Surface Phase C/D、替代 alpha 候選為當前路徑。
- **EDGE-P2-3 Phase 1b**：Round 1 Design/Governance + Worktree B 部署已 CLOSED（細節見 archive 2026-05-16 + 2026-05-19 v55 translation archive）。本 refactor 是 execution-quality optimization（fee saving ~$50-$200/年，per E3 empirical），不解 trading losses root cause；真實治癒走 W-AUDIT-8a/8b/8c alpha source 軸。
- **Trading losses Round 2 — Alpha Source Push**：Option A source/test + W-AUDIT-8c correction + V095 apply 已 DONE。C1 transport proof passed 2026-05-17，writer revival 已上線（`0e8a8ae8` / `bedc40c3`）。
- **2026-05-18 EDGE-P2-3 Phase 1b RUNTIME ACTIVATOR**：RESOLVED via deploy chain CLOSED；engine PID 1143103；`runtime.use_maker_close=true`。AC-A 24h 統計顯著性窗口已通過 INSUFFICIENT_SAMPLE 階段。
- **2026-05-18 W-AUDIT round 2 結局**：
  - W-AUDIT-8b Round 2 RED_FINAL **TOMBSTONED**（4-agent 4/4 APPROVE concur；spec v0.4 + AMD v0.7）
  - W-AUDIT-8a Phase B/C/D Wave 1 **MERGED**（B-REM-1 / B-REM-5 + ADR-0023 / C1-LIQ-WRITER + `[67]`）
- **2026-05-18 multi-agent dispatch race incident**：lesson learned = 不再多 E1 同時並行；single-agent sequential + E2 鏈完才下個（已 enforce）。
- **2026-05-18 Phase 1b parameter calibration**：12H sample 100% timeout_taker fallback → P0 calibration DONE 2026-05-18 13:50 UTC（top cell `G-AB-01-C90` fill 70.8% / +3.37 bps simulated；Grid family `timeout_ms 30s → 90s` deployed）。Phase 2a 14d observation clock reset @ 13:50 UTC。
- **2026-05-19 v55 sprint**：4 軌道 closure（見 §0）。
- **2026-05-19 ~20:00 UTC v56 incident**：engine 7h43m trading-inert（見 §-1）；新 P0 `P0-ENGINE-HALTSESSION-STUCK-FIX`；PA spec 已派；engine PID 2099215 自 20:09:36 起恢復；Phase 1b verification 繼續累積。

---

## §4 活躍派工佇列

**狀態圖示**：✅ DONE / ⏳ PENDING / 🟡 PARTIAL / 🔵 ACTIVE / ⛔ DEFER

### §4.1 Wave Roster（DUAL-TRACK + 8a-8h）

| 序 | Wave | 標籤 | Owner | 狀態 | 出口條件 |
|---:|---|---|---|---|---|
| 1 | `W-F` Edge/data quality + Live Gate 基座 | alpha-bearing | PM→QC/MIT/PA→E1/E4→PM | ⏳ **PENDING**（true-live 前置）| H0 production caller / pricing binding / supervised-live state machine |
| 2 | `W-G` Proposal/approval/mobile relay | alpha-neutral | PM→CC/FA/PA→E1/E2/E4→PM | 🟡 **BACKEND 基座 DONE**（待 mobile relay）| Gateway/console proposal/approval relay；不可直發 order/config/live-auth |
| 3 | `W-AUDIT-4` ML 基座 + dead schema | alpha-bearing | E1×6 + MIT + E2 + E4 | 🟡 **PARTIAL** | 修正後保留範圍見 §11.2；長尾治理 mount 進 `W-AUDIT-8f` |
| 4 | `W-AUDIT-8a` Alpha Surface 基座 | alpha-bearing | PA→E1→E2→E4 + MIT/QC/CC/BB→PM | ✅ **C1 transport PASS + writer revival + Wave 1 MERGED**（細節歸檔）| Wave 2（C2-ORDERFLOW / C3-SPREAD / D-CONTRACT-LOCK）DEFER Sprint N+4 |
| 5 | `W-AUDIT-8b` A4-A Funding Skew Directional | alpha-bearing | PA→Stage 0R→QC/MIT/BB | ⛔ **TOMBSTONED 2026-05-18**（Round 2 RED_FINAL；no-revive on same feature shape）| Redirect→W-AUDIT-8c + W-AUDIT-8a Phase B/C/D |
| 6 | `W-AUDIT-8c` A4-B Liquidation Cluster Reaction | alpha-bearing | PA→E1→E2/E4→MIT→BB→PM | ✅ **SOURCE/TEST + V095 LINUX APPLY + WRITER REVIVAL DONE**（細節歸檔）| 策略 launch 仍另立 Stage 0R/design gate |
| 7 | `W-AUDIT-8e`（R-2）Strategist Alpha Source Orchestrator | alpha-bearing | PA spec→E1 IMPL | ⛔ **DEFER** N+4 spec → N+5 IMPL | AlphaSourceRegistry + dynamic Sharpe-by-regime + Hypothesis sourcing |
| 8 | `W-AUDIT-8f`（R-3）Hypothesis Pipeline + W-AUDIT-4 ML | alpha-bearing | PA spec→E1 IMPL + MIT spec | ⛔ **DEFER** N+5 IMPL | learning.hypotheses state machine + dead schema 收尾 |
| 9 | `W-AUDIT-8g`（R-4）Per-alpha-source Live Promotion Gate | alpha-bearing | PA spec→E1 IMPL | ⛔ **DEFER** N+7+ | LiveBudget(alpha_source_id, slice) 取代系統級 live_reserved |
| 10 | `W-AUDIT-8h` Alpha Sources GUI tab + Hypothesis Lab GUI tab | alpha-neutral | E1a + A3 | ⛔ **DEFER** N+4-N+6 | A3 tab expansion follow-up |
| 11 | `W-AUDIT-10`（R-5）Spec-as-Code + Module Lifecycle SM | alpha-neutral | PA spec→E1 IMPL | ⛔ **DEFER** 中期 | CI gate spec drift > 7d auto-fail + 模組/表 lifecycle 標頭 |
| 12 | `EDGE-P2-3 Phase 1b` Close-Maker-First Refactor | alpha-impact-adjacent execution-quality | PA→E1→E2→E4→QA→PM | ✅ **DEPLOY DONE 2026-05-18**（細節歸檔）| Phase 2a 14d observation clock reset @ 13:50 UTC；24h AC-A SQL verify ~2026-05-19 13:50 UTC |

### §4.2 跨 Wave 衝突仲裁（4 條，PA §3.3 必繼承）

| # | 衝突 | 範圍 | 解 |
|---|---|---|---|
| 1 | W-AUDIT-8a Phase A migration ↔ W-AUDIT-6d mid-ground 5 策略改動 | `bb_breakout/mod.rs` / `ma_crossover/strategy_impl.rs` / `bb_reversion/mod.rs` | 序列化：先 6d mid-ground，再 8a Phase A |
| 2 | W-AUDIT-9 T3 shadow_mode_provider stage-aware ↔ ExecutorAgent shadow_mode 接線 | `executor_config_cache.py` / `executor_agent.py` | W-AUDIT-3b 必先 land；T3 結束前 ExecutorAgent shadow=true 不動 |
| 3 | W-AUDIT-8a Phase B+C ↔ W-AUDIT-5b 性能 wave | `tick_pipeline/mod.rs` | Phase B+C 並行於 N+1，5b 性能 catch-up reserved slot |
| 4 | A 群策略候選 ↔ W-AUDIT-9 Stage 1 Demo cohort 選擇 | governance/canary | **RESOLVED 2026-05-16**：Stage 1 為 Demo-only；A4-C tombstoned，不可作 cohort 來源 |
| 5 | TODO `W-AUDIT-8b/8c` ↔ legacy execution_plan `8b/8c` 檔名 | `docs/execution_plan` | **TODO IDs 為 SoT 2026-05-15**：`8b` = A4-A Funding Skew，`8c` = A4-B Liquidation Cluster；舊 `w_audit_8b_strategist...` / `w_audit_8c_hypothesis...` 是 R-2/R-3 alias（現為 `8e/8f`），不可拿來當策略 spec |

---

## §5 Sign-off Delta

完整 Sprint N+0 22-invariant ledger 已歸檔（v21 cleanup archive）。當前 delta：

- ⛔ **A4-C active-promotion marker 已移除 2026-05-16**：Step 5b / RCA 封存 no-revive；只留 tombstone guard 與 diagnostic panel 引用。
- 🟡 **OI-confirmed 5m Stage 0R packet 非 promotional**：定義 `bb_breakout_oi_confirmed_5m` replay 接受規則；read-only feasibility probe 樣本量 < Stage 0R 下限（`n=9` pooled；每 symbol < 100）且 gross 15m 為負，不能作 promotion 證據。
- ⏳ **A 群 alpha-source 不變量**：`declared_alpha_sources()` vs real logic re-check 待新 alpha 候選 land 後再啟。
- 🟡 **W-AUDIT-4b 修正後範圍**：透過 §11.2 retained tables/views/drop scope 維持 active；`P1-WA4B-INSERT-1` 已完成。
- `[55]`、W-AUDIT-3b、F-08 cron、`P0-MIT-LABEL-CLOSE-TAG-1` 細節已歸檔（v36 cleanup archive）；剩餘 edge 風險仍由 `P0-EDGE-1` 追蹤。

---

## §6 當前 W-AUDIT 優先順序

PM/PA/FA 三方交叉檢查後：

1. **True-live 仍 blocked**：被 `P0-EDGE-1`、`P0-LG-1/2/3`、`P0-OPS-1..4`、新 `P0-ENGINE-HALTSESSION-STUCK-FIX` 卡住。2026-05-15 之後的 runtime/doc 修正不授權 live。
2. **Stage 1 Demo micro-canary 仍 blocked**（非 active execution）：無 active paper cohort，無 A4-C cohort 候選；launch 需未來 strategy×symbol Stage 0R packet 且 `eligible_for_demo_canary=true` + AMD-2026-05-15-01 內 runtime/lineage/operator gates 全通。
3. **Alpha path 優先**：`W-AUDIT-8b` 已 tombstoned；`W-AUDIT-8a C1` technical PASS；W-AUDIT-8c source/test 修正 + V095 apply + writer revival 全 DONE。業務鏈根因仍為缺乏非教科書 alpha。
4. **Runtime blocker 更新**：`[27]`、`[55]`、`[67]` 已 closed；不解鎖 Stage 1 Demo（無綠燈 alpha Stage 0R cohort）。新增 v56 P0 incident 須先 spec→IMPL→deploy 才能釋出 7d Linux soak。
5. **Maintenance**：P2 hygiene 排在 alpha / LG / ops gates 之後；W-AUDIT-5 damaged dump cleanup 與 W-AUDIT-7 F-07/CEA env 已 ops-closed 2026-05-15。

### §6.1 A4-C BTC→Alt Lead-Lag Tombstone（2026-05-16）

`W-AUDIT-8d` A4-C 非 active promotion task。active docs 僅保以下 guard：

- 狀態：archived from promotion；diagnostic-only / no-revive（BTC 1m return + xcorr feature shape）
- 保留：`panel.btc_lead_lag_panel`、`[57] btc_lead_lag_panel_health`、歷史 rows（供未來 Hypothesis Pipeline 探索）
- 不保留：Stage 0R 候選 / Stage 1 Demo cohort 來源 / paper-based promotion 措辭 / threshold-only revive tasks
- 未來重啟：materially new predictive variable + preregistered validation + 全新 strategy×symbol Stage 0R packet 且 `eligible_for_demo_canary=true`

詳細 Step 5b / RCA / PM+QC+MIT verdicts 歸檔於 `docs/execution_plan/2026-05-15--a4c_btc_alt_lead_lag_archive_verdict.md` 與相應 archive。

---

## §7 W-AUDIT-6d Mid-Ground

詳細 保 6 / 砍 6 ledger 與 DSR K -12 推導已歸檔（v21 cleanup archive）。

**保留 active rule**：6 polishing 項仍 REJECT，未經未來 QC/PM 決議不可重啟；不可新增 per-symbol / per-threshold sweep（會膨脹 DSR trial count）。

---

## §8 D-02 Layer 2 手動 7d 試運行 SOP（Operator 自執行）

完整 6 步 SOP 見 FA report `2026-05-09--full_dispatch_business_chain_validation.md` §2。摘要：

1. **API key 取得**：Anthropic Console → Create Key（命名 `openclaw-layer2-manual-7d-trial`，monthly budget $5）
2. **寫入**：`echo "sk-ant-xxx..." > $OPENCLAW_SECRETS_ROOT/secret_files/anthropic/api_key && chmod 600`
3. **每日手動觸發 7d**：`curl -X POST http://localhost:8000/api/v1/layer2/run_session -d '{"trigger_kind":"manual_daily_probe","scope":"L1_triage","max_cost_usd":0.50}'`
4. **7d 4 指標觀察**：cost_today / decisions_assisted / avoided_loss / false_positive_rate
5. **Pass**：alpha > 2× cost + false_positive < 40% + 0 critical incident；**Fail**：alpha < cost OR false_positive > 60% OR ≥1 layer2 建議致 > 5 USDT 虧損
6. **Fail rollback**：`rm api_key && restart_all.sh --keep-auth`

**FA constraint**（invariant 15）：D-02 SOP 不可自動化為 cron / event-trigger（會違 ADR-0020 manual+supervisor-only）。預期 +2-5 USDT/week alpha；7d < 1 USDT/week 不值人工成本 → 建議 abort。

---

## §9 Dormant D-XX 區（FA §5.2 必 explicit + reason）

| D-XX | 描述 | 狀態 | 原因 | 最早重啟 |
|---|---|---|---|---|
| D-13 | Cognitive Modulator | DORMANT | 3-Tier `consecutive_loss/weekly_pnl` 數據源未接齊 + alpha 無依賴 | Sprint N+8+ |
| D-14 | DreamEngine 完整自主進化 | DORMANT | Foundation Model + L4 跨策略 meta-learning（ADR-0020 限 manual）；Foundation Model 未 ready | long-tail |
| D-15 | OpportunityTracker 全 Agent 注入 | DORMANT | 不影響 supervised live；Sprint N+5 可選 | Sprint N+5 可選 |
| D-16 | openclaw_core 9 模組 sunset cleanup | DORMANT | ADR-0015 已標 permanent sunset candidates；其中 7 模組已被 `P2-DEAD-RUST-CLEANUP-1`（2026-05-18 commit `449f628b`）清除，餘 2 待 PA 下 sprint 確認 | Sprint N+6+ |
| D-17 | Layer 2 自主推理循環自動觸發 | **PERMANENT DORMANT** | ADR-0020 manual+supervisor-only by design | **不解** |

**FA constraint**：靜默漏寫 = 6 個月後 lobby 重新 review；explicit 標 dormant + reason + earliest reactivate = 防 strategy drift。

---

## §10 P0 — True-Live Blockers

| ID | 狀態 | 任務 | 接收條件 |
|---|---|---|---|
| `P0-ENGINE-HALTSESSION-STUCK-FIX` | 🔵 **NEW 2026-05-19 ~20:00 UTC — PA spec 已派，operator 語意已鎖** | **Incident**：engine PID 1942669（UTC 12:27:11 start）處理 FILUSDT halt_session emergency close 後（12:27:14 + 12:27:37）進入 **TRADING-INERT 7h43m**，直到 operator UTC 20:09:36 restart → 新 PID 2099215。**E2 RCA verdict**（`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-19--engine_watchdog_respawn_loop_and_trading_inert_rca.md`）：`paper_paused=true` set by Step 6 `RiskAction::HaltSession`（`step_6_risk_checks.rs:434-461`）**無 TTL auto-clear**；只 4 種 clearer（IPC Resume / Reset / SystemMode::ShadowOnly / restart default init）。與先前 `P1-WATCHDOG-STATUS2-RCA` 不同根因（後者只覆 systemd cosmetic `sys.exit(2)`）。Watchdog 無 "alive but inert" 偵測（只看 snapshot freshness；engine 每 30s 寫 status_report 不論交易狀態）。**Operator 決議 2026-05-19 ~20:30 UTC**：Layer A = **TTL clear daily_loss only / drawdown stays sticky**；Layer B = watchdog business-heartbeat probe（alarm-only，no auto-restart）。**修復層**：Layer A daily_loss-only TTL（鏡像 `news/guardian_impl.rs:60-145` 模式）+ halt_kind 分類 + forensic halt_audit.log + 跨 restart 狀態持久化 + audit lifecycle row；Layer B watchdog probe `TRADING_INERT_PROLONGED`（parse pipeline_snapshot.json intents/fills/paper_paused；60min threshold；cooldown；reset）。**Acceptance**：simulated daily_loss halt + 1h TTL → auto-clear PASS；simulated drawdown halt + 1h+TTL → 仍 paper_paused=true；watchdog probe 在 test scenario 內 60s 觸發告警；7d Linux run 0 false positive；engine_mode demo/live_demo/live 全覆。**PA 已派 spec**：`docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md`（~600-1000 LOC，ETA 2-3h）。**Halt 觸發 UNRESOLVED**：log rotation 失了 UTC 12:27 line；數學（drawdown 10.2% vs TOML 25% threshold）不通 — 可能 IPC patch / loading-order race / 第三條路徑；PA spec 必含 halt_audit.log 強制留證。**Severity P0**（下次 breach 必復發；demo/live_demo/live 共用代碼；Phase 1b verification + 所有 PnL 暴露）。 |
| `P3-AGENT-SPINE-BENCH` | ⏳ scheduled N+3 | emit_entry_lineage / emit_fill_completion bench harness | E5：當前只有 tick_pipeline hot_path_baseline；補 1000×100 sample SLA monitoring |
| `P3-SPINE-COUNTER-CACHE-ALIGN` | ⏳ scheduled quiet period | 3 AtomicU64 counter `#[repr(align(64))]` cache line | E5 cosmetic；10 min fix；~50-200ns 額外延遲降到 0 |
| `LG-1` H0 production caller | ✅ **IMPL LANDED 2026-05-11** (`a11a4df6` + closure `0fb661d3`) — 待 7d observation | T1+T2+T3+T4 E1×4 並行 IMPL DONE；E2+E4+E5+A3 全 APPROVE；runbook `docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md` ship；**2026-05-19 PM audit TODO 同步斷裂修正** | per PA plan §1.4 |
| `LG-2` Provider pricing binding | ✅ **IMPL LANDED 2026-05-11** (`a11a4df6` + closure `0fb661d3`) — 待 7d observation | T1+T2+T3+T4 全 land；FeeSource enum + query_fee_source IPC + PricingConfig + Live spawn assertion；runbook `docs/runbooks/2026-05-11--lg2_pricing_assertion_failure.md` ship；**2026-05-19 PM audit TODO 同步斷裂修正** | per PA plan §2.4 |
| `LG-3` Supervised live SM | ⚠️ **SPEC v2 READY 8 days, Wave 2.4 IMPL DISPATCH PENDING** — 2026-05-19 PM audit catch silent stall | PA spec v2 final `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md`（1767 行，26 caveats incorporated：10 QC + 9 MIT + 7 BB）+ QC/MIT/BB 3-review 全 APPROVE 2026-05-11；**V094 號被 W-AUDIT-8c 佔用→必改 V099/V100**；Wave 2.4 IMPL E1×7 需 PA refresh dispatch plan（V### 號 + multi-E1 race-aware 排程 + 與 v56 P0 序列化）；**序列化於 v56 P0-ENGINE-HALTSESSION 完整 cycle 之後**派 | per PA plan §3.6 + §6.1 + §6.4；refresh plan dispatched 2026-05-19 |
| `P0-EDGE-1` | ACTIVE | Edge net-positive 決議 | 策略 edge 須 net-positive 或限定 supervised path；根因連到 `P0-MIT-LABEL-CLOSE-TAG-1` 1-day fix（最高 ROI） |
| `P0-LG-1` | 🟢 **IMPL LANDED, 待 7d observation closure** | H0 wired into production decision path + metrics + fail-closed (LANDED 2026-05-11) | E2+E4+E5+A3 APPROVE；evidence: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--wave2_2_lg1_lg2_e2_review.md` |
| `P0-LG-2` | 🟢 **IMPL LANDED, 待 7d observation closure** | Fee/pricing source 綁定、freshness 檢查、startup assert (LANDED 2026-05-11) | FeeSource enum + IPC + PricingConfig + Live spawn assertion 全 ship |
| `P0-LG-3` | ⚠️ **SPEC READY, Wave 2.4 IMPL DISPATCH PENDING** | Live authorization / lease / drawdown / revoke / operator approval 全顯式且測過 | spec finalize 2026-05-11；2026-05-19 PM audit catch 8d silent stall；Wave 2.4 IMPL 序列化於 v56 P0 完整 cycle 之後派 |
| `P0-OPS-1..4` | ACTIVE | HTTPS / credential rotation / legal+ToS / first-day runbook | True-live 前置 |

已完成 P0 條目（如 `P0-PHASE-1B-PARAM-CALIBRATION-1`）已歸檔於 `docs/archive/2026-05-19--todo_v55_translation_archive.md` 與 v36 cleanup archive。

---

## §11 P1 — 下個工程佇列

### §11.1 Sprint N+0 Active

已標完成歸檔於 v21 cleanup archive。當前活躍工作從 §10 / §11.2 / §11.3 開始。

### §11.2 W-AUDIT-4b 修正後保留範圍（invariant 19）

| ID | 物件 | 修正後分類 | Owner | 備註 |
|---|---|---|---|---|
| `P1-WA4B-INSERT-2` | `learning.cost_edge_advisor_log` | retained INSERT table / row-growth 已驗 | E1 | Writer live at `cost_edge_advisor/mod.rs`；2026-05-14 runtime 6091 rows。當前 demo `[cost_edge].enabled=false` → rows 為 `Disabled` / `ratio=NULL`；ratio-present rows 需另立 config 決議 |
| `P1-WA4B-INSERT-3` | `observability.drift_events` | retained INSERT table / readiness gated | E1 | Writer 在 `drift_detector.rs` 並在 `tasks.rs` spawn；依賴 active `feature_baselines` 與配置的 ADWIN burn-in（預設 30d）。不可未經 operator 同意移除 burn-in |
| `P1-WA4B-VIEW-1` | `learning.mlde_edge_training_rows` | companion VIEW | E1/MIT | 唯讀投影，非 INSERT 路徑。合約掛 ML training-data healthcheck |
| `P1-WA4B-VIEW-2` | `learning.scorer_training_features` | companion VIEW | E1/MIT | 唯讀投影；full unbounded count 成本高，請用 bounded/metadata probe |
| `P1-WA4B-DROP-1` | `learning.scorer_predictions` | dropped / no-DDL target | E1/MIT | V069 已 drop；無 producer 接線目標，除非未來 spec 重建 |

`P1-WA4B-INSERT-1` 完成細節歸檔於 v36 cleanup archive。

### §11.3 P1 — 其他活躍

| ID | 優先級 | 任務 | 備註 |
|---|---:|---|---|
| `P1-DATA-1..3-WATCH` | 3 | Runtime-reloaded WARN cluster row-rolloff watch | source 已修；保留 observation-only watch |
| `P1-EDGE-1..2` | 3 | ma_crossover/grid blocked_symbols 已 frozen + funding_arb 14d audit 2026-05-16 | 維持 freeze + 2026-05-16 audit |
| `P1-LG-5` | 4 | LG-5 reviewer maturity watch | source 活躍；audit-row 健康 |
| `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` | 4 | spec §5.4 完整 dynamic backoff state machine IMPL（per-symbol 1s exp → 60s + ≥10 symbol cascade → 5min global pause + audit row `rate_limit_scope="global"`）| Phase 1b 初版（commit `27f02a07`）取 per-symbol 5min 固定避 scope creep；Phase 2a Demo PASS 後另開 PR；PA 估 ~50 LOC state machine + ~80 LOC integration test |
| `P1-WATCHDOG-NETOUTAGE-CLASSIFIER-FIX` | 2 | **NEW**：STATUS2 RCA 衍生 source-only follow-up。`engine_watchdog.py` 當前需 ≥5 連續 network-error lines in active `/tmp/openclaw/engine.log`；rotated/interleaved DNS outage 證據可能 default 到 `engine_crash` 觸發 restart storm。需 recent-log classifier 加固 + regression test，再依 3-strike stability 動作 |
| `P1-WATCHDOG-EXIT-CODE-CLARIFY` | 3 | **NEW（v55）**：watchdog exit code 語意明確化（sys.exit(2) → 20 之類）以利 systemd / 上層觀察 |

> v55 衍生：`FA-WATCHDOG-3STRIKE-ESCALATION-POLICY` 待 FA 設計後分配優先級。

歸檔的 P1 條目：v36 cleanup archive + 2026-05-19 v55 translation archive。

### §11.4 P0-MICRO-PROFIT — 微利根因治本路徑（2026-05-11 QC audit 拍板）

**背景**：QC 2026-05-11 audit verdict — 「為何盈利都是超微利潤」+「能否放大」。判定：當前 5 textbook 策略 7d EV<0（-17.82 bps demo）；**任何 sizing 槓桿 L>1 必放大虧損**（數學常數）。先修 alpha，再談 size。

**5 root cause + 占比**：
1. **Alpha 結構性缺失（~60%）** — 5 textbook 策略 post-publication decay
2. **Account size × 0.1% TOML 物理上限（~20%）** — $591 × 0.1% = $0.59/trade 設計上限
3. **Fee drag（~10%）** — 10.4% taker remnant + PostOnly missed-trade
4. **Signal target tight 設計（~5%）** — grid 22bps / bb 1-2σ / ma sub-1ATR
5. **Slippage + queue position adverse selection（~5%）**

**治本路徑 = PA R-1/R-2/R-3 redesign（已映射 W-AUDIT-8a..8f wave 矩陣）**：

| ID | 任務 | Spec 來源 | ETA |
|---|---|---|---|
| `W-AUDIT-8a` Phase B/C/D | Tier 2 panel collector + Tier 3 microstructure + Tier 4 information flow | Sprint N+1 W2 起 | 4-6 sprint |
| `W-AUDIT-8b`（A4-A）| Funding Skew Directional（R-1 IMPL）| ⛔ **TOMBSTONED 2026-05-18** | — |
| `W-AUDIT-8c`（A4-B）| Liquidation Cluster Reaction | ✅ source/test + V095 apply + writer revival DONE | 策略 launch 仍另立 Stage 0R/design gate |
| `W-AUDIT-8d`（A4-C tombstone）| BTC→Alt Lead-Lag diagnostic panel | Archived guard only | ⛔ 不再 active；diagnostic-only |
| `W-AUDIT-8e`（R-2）| Strategist Alpha Source Orchestrator | W-AUDIT-8b/8c/8d 後 | N+3-N+4 |
| `W-AUDIT-8f`（R-3）| Hypothesis Pipeline first-class（含 W-AUDIT-4 ML 6 dead schema 併入）| 序列化於 R-2 後 | N+4 |

**Total ETA = 12-17 sprint（3-4 月）** — 真實 gross 轉正最早窗口。

**Operator 5 zero/small cost action（2026-05-11 拍板）**：
1. ✅ DONE：修 `feedback_position_sizing` memory drift（3% → 註明 SSOT 0.1%/0.05%）
2. ⏳ PASSIVE wait：等 7d 重測 §3 [40]
3. ⏳ INFO gathering：Bybit fee tier 距 VIP1 還差多少 30d trading volume（被動 ROI ~0.5-1 bps RT）
4. ⏳ PASSIVE wait：TONUSDT 30d evidence → P1-CONDITIONAL-WATCH freeze 決議（2026-06-09 收口）
5. ✅ DEFER 記錄：D/E sizing 槓桿等 ML calibration N≥200 — 寫入 backlog 防過早 commit

**11 sizing 槓桿全 REJECT in current EV<0 state**（A/B/E/F = REJECT；C/I = CONDITIONAL；D = NEUTRAL；G/H/K = DEFER；J = APPROVE 被動）。

**Operator 守則**：
- 看見 memory「3%」**不要**直接套到 TOML（先讀 risk_config_*.toml SSOT）
- 任何「升 TOML sizing」提案在 EV<0 條件下 = 災難（先修 alpha）
- 信 config，不信 memory（per `math-model-audit` S1）

**Source**：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-11--p1_micro_profit_amplification_math_analysis.md`

### §11.5 EDGE-P2-3 Phase 1b — Final Dispatch Plan 摘要

**Status**：Round 1（Design + Governance）closure + 30+ commit timeline + 4-agent verdict + IMPL Prereq status + next-round scope → 歸檔 `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`。Phase 1b main source/test 完成於 `ea4ceca6`；V094 Linux apply + engine-only deploy/restart 完成 2026-05-17。

**仍 active**：
1. ❌ `P0-EDGE-1` — `[40]` negative realized edge 仍 active
2. ⛔ `W-AUDIT-8b Stage 0R` — **TOMBSTONED**（細節歸檔）
3. ✅ `W-AUDIT-8a C1` — v2 24h proof technical PASS + writer revival DONE 2026-05-17
4. ✅ `P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG` — DONE 2026-05-16
5. ✅ `P1-BBMF3-WIRE-1` — source/test + V094 apply + engine-only rebuild/restart DONE 2026-05-17
6. ✅ `W-AUDIT-8c` — source/test 修正 + V095 dry-run/MIT re-sign + Linux apply + writer revival DONE 2026-05-17。策略 launch/promotion 仍 future gate

**Runtime kickoff status**（精簡）：
- V094 Linux migration/deploy 授權 → deploy-chain regression → post-deploy healthcheck → PM sign-off：✅ DONE 2026-05-17
- Phase 1b runtime activation：✅ **DEPLOY DONE 2026-05-17 23:54 UTC**（engine PID 1143103）
- Calibration sweep + Rust timeout deploy：✅ **DONE 2026-05-18 13:50 UTC**（engine PID 1506208；grid family timeout 30s→90s）
- **Phase 2a 14d observation clock 已 reset @ 2026-05-18 13:50 UTC**；24h post-deploy AC-A SQL verification target ~2026-05-19 13:50 UTC
- Cross-wave consistency check pending（QA recommendation #3）
- Outstanding anomaly investigations（low-priority parallel SD agent 2026-05-18 dispatch）：SD-1 A axis（offset_bps）dead-variable / SD-2 PS family（phys_lock_gate4_stale_roc_neg）100% n_skip / 0 fill — 報告 `2026-05-18--phase_1b_calibration_sweep_anomalies_sd_report.md`
- 後續：24h AC-A real verdict → if PASS 繼續 Phase 2a 14d / if FAIL revert timeout 90s→30s 或 PA tune-further；Phase 2b LiveDemo / operator + AMD live carve-out / Phase 3 Mainnet 仍 future gate
- **v56 incident 衝擊**：2026-05-19 ~12:27-20:09 UTC 7h43m trading-inert 中斷 Phase 1b verification；engine 自 20:09:36 起新 PID 2099215 恢復，sample 繼續累積（n=13 起）。verdict 視窗（T+96h~T+120h，2026-05-22~23 UTC）不受影響但 sample velocity 有缺口。

### §11.6 12-Agent Full System Audit WPs（2026-05-16）— follow-ups

- **Source**：`srv/2026-05-16--full-system-audit-fix-plan.md`（PA consolidated + PM sign-off）
- **Wave 1-4 source/test**：完成並歸檔於 v36 cleanup archive

**剩餘 active follow-up**：
- WP-11 Phase 2 residual → §12 P2 backlog
- WP-12 ONNX 仍 deferred；rule-based fallback 為當前行為
- PA audit drift hardening → `P2-PA-CALLPATH-GREP-RULE`（已 DONE）
- LOC follow-up → `P2-COMMON-JS-LOC`（DONE）、`P2-TAB-LIVE-LOC`（DONE via JS extract）

---

## §12 P2 — 維護 backlog

| ID | 任務 | 觸發 |
|---|---|---|
| `P2-LEASE-1` | 清掃 terminal `DecisionLeaseSm.objects` Vec entries | 長期 soak 出現 memory growth 或 high-volume live 前 |
| `P2-STRUCT-2` | Zombie / deprecated code 盤點 | 下一次架構 hygiene sweep |
| `P2-AUDIT-DEAD-CODE` | openclaw_core 9 模組 sunset（D-16 dormant）| ADR-0015 + AMD-2026-05-09-02 accept；Sprint N+6+ |
| `P2-AUDIT-VERIFY-3` | W-AUDIT-4 dead schema 真實 fix → mount 進 `W-AUDIT-8f`（R-3）Hypothesis Pipeline | Sprint N+5 |
| `P2-ENTRY-CLOSE-MAKER-REAL-FILL-FIX` | **NEW（v55 衍生）**：entry-close vs risk-exit limit placement / order lifetime / cancel-fallback sequencing / queue+trade-tape evidence 比對；不得只用 sweep proxy 調 runtime 參數 | source/test follow-up |
| `P2-WP05-CSP-UNSAFE-INLINE` | 🟡 SRI 部分 DONE 2026-05-18；完整 CSP nonce-based refactor 待 live-gate 前 P1 | live-gate 前 |
| `P2-QA-TEMPLATE-CLOSE-MAKER-SPLIT-FIX` | **NEW（v55）**：QA 模板「entry-close vs risk-exit」拆法改用 attempt × fallback 而非 ID prefix | 下一次 QA template 更新 |
| `P2-SIM-QUEUE-AWARE-ADJUSTMENT` | **NEW（v55）**：replay queue-aware bias 修正（10-15pp）| 下一次 sim harness round |
| `P2-STRESS-BB-BREAKOUT-FALSE-SQUEEZE-COINCIDENTAL-PASS` | **NEW（v55）**：3rd 測試因「錯誤原因」PASS — 改善 assert 條件 | 下一輪 stress harness 維護 |

**已完成 P2 條目（細節歸檔於 2026-05-19 v55 translation archive）**：
- `P2-DEAD-SCHEMA-DROP-1` ✅
- `P2-DEAD-RUST-CLEANUP-1` ✅
- `P2-PERCEPTION-DEPRECATE-1` ✅
- `P2-H0-DISPLAY-LABEL-1` ✅
- `P2-ORDERS-INTENT-ID-WRITER-GAP-1` ✅
- `P2-WP05-FUP-1` ✅ 32/32 全收
- `P2-COMMON-JS-LOC` ✅
- `P2-ENTRY-PATH-0PCT-MAKER-FILL-RCA` ✅
- `P2-TAB-LIVE-LOC` ✅ via `P2-TAB-LIVE-JS-EXTRACT`
- `P2-CROSSTAB-I18N` ✅
- `P2-STOCHASTIC-LEAK` ✅
- `P2-START-LOCAL-HELPER` ✅
- `P2-PA-CALLPATH-GREP-RULE` ✅
- 5 個 `P2-PORTFOLIO-RESTING-*` follow-up ✅

完成的 Sprint N+2 P2 條目（`P2-N2-1..4`）歸檔於 v36 cleanup archive。

---

## §13 Push Back / Risk 治理記錄（不可漏失，FA §5.6）

### PA Push Back（已 RESOLVED 2026-05-09 operator (a)）
- **原 risk**：Sprint N+0 5/5 HOT capacity = 任一 E1 故障 = 阻塞 critical path
- **Operator 拍板 (a)**：提供 1 stand-by E1，Sprint N+0 capacity 升 6 並行（5 active + 1 stand-by）
- **記錄**：v19 §0 Sprint Banner / §5.4 invariant 22 / §6 Day 0-3 dispatch

### FA Push Back（採納，記入治理）
1. Track W vs Track A 預算 — Track W 92h 是 supervised live 前置門檻（合規 / 安全 / 可觀測 baseline），**不能被 Track A lobby 取代**
2. D-02 SOP 預期上限 +2-5 USDT/week；7d < 1 USDT/week 不值人工 fixed cost → 建議 abort
3. A/B/C 候選預期 +3-7% 業務鏈是中位估，新 alpha source **0% PASS 率歷史不支持「三都 PASS」樂觀情境**
4. W-AUDIT-6d 砍 6 polishing 是 DSR 數學意義 right move（K -12），不是省工時妥協

### 4-agent loss audit cross-fact-check（撤銷的 stale belief）
- **QC v2-NEW-4 Donchian「runtime contaminated」過期 belief**：MIT 校核 + PM 直接驗證確認 runtime 自 `75741eff`（2026-04-28）起 leak-free 11 天；`ad14db07` 僅補 regression test。後續 audit / push back 不可再引此 finding 為 active runtime issue。

---

## §14 排程

| 日期 | 工作 | Gate |
|---|---|---|
| 2026-05-10..16 | Sprint N+0 W1-W2 FOUNDATION HEAVY | Closed；細節歸檔於 v21 cleanup archive |
| 2026-05-16 | funding_arb 14d audit | verification/history；retirement 決議於 AMD-2026-05-09-02 / ADR-0018 |
| 2026-05-17..23 | Sprint N+1 ALPHA SURFACE PANEL WIRING | 8a C1 transport proof passed；8c source/test 修正 + V095 dry-run/MIT re-sign + Linux apply 完成；writer revival 完成（v46）；8b read-only Stage 0R query/report packet；Stage 1 Demo 限未來綠燈 Stage 0R 後 |
| 2026-05-24..30 | Sprint N+2 8a Phase D + Stage 2 demo cohort 14d | Stage 2 限 Stage 1 Demo 實證後 |
| 2026-05-31..06-06 | Sprint N+3 8c（Liquidation）IMPL + 8e（R-2）spec + Stage 3 demo full | |
| 2026-06-07..13 | Sprint N+4 8f（R-3）spec + 8b（Funding Skew）IMPL + 8e IMPL + Track W 收尾 | Track W 全 closed |
| 2026-06-14..20 | Sprint N+5 8f IMPL + 8g（R-4）spec + 首個 per-alpha-source supervised live | 業務鏈 85-89% |
| 2026-06-15 | Supervised live 樂觀帶（業務鏈 75%+）| conditional on W-AUDIT-1..7 + 5 P0-LG/OPS + W-A/B/C/D PASS |
| 2026-06-30 | Supervised live 中位帶（業務鏈 80%+）| ~40% probability per FA |
| 2026-07-15 | Supervised live 悲觀帶（業務鏈 85%+）| ~25% probability per FA |

---

## §15 派工規則 + Handoff 檢查

### 派工規則
- PM-first triage for every wave
- 實作工作：`PM → PA → E1/E1a → E2 → E4 → QA → PM`，跳過角色需 explicit justify
- 安全 / 部署 / runtime：`PM → E3 → BB（若涉交易所）→ PM`
- 量化 / 資料決議：`PM → QC → MIT → AI-E（若涉模型成本）→ PM`
- 每個 green checkpoint 提交 subject + body，push origin，再以 fast-forward 同步 Linux
- 非 CI-relevant commit（doc / governance / TODO update / report land）加 `[skip ci]` 保 CI 額度
- 不可 rebuild / restart / 動 live auth / 改 scanner evidence contract / 解鎖 executor shadow / 啟 lease-router / 新增 OpenClaw write/proposal 路徑，除非 operator 顯式授權
- W-AUDIT-6d 砍 6 子項：E2 必 grep blacklist；命中即 reject merge
- **新增（v55 governance flag）**：sign-off SOP 加 `cargo test -p openclaw_engine --release`（no --lib）以覆蓋 tests/ integration crate

### Handoff 檢查

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

---

## §16 References

### 4-Agent Loss Audit（2026-05-09）
- **PA dispatch plan**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_dispatch_engineering_plan.md`（commit `d3bf7be2`，689 行）
- **PA architectural redesign**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`
- **PA merge analysis**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--todo_qctodo_merge_analysis.md`
- **FA business chain validation**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_dispatch_business_chain_validation.md`（commit `5a2dee98`）
- **FA dormant alpha inventory**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_loss_dormant_alpha_features_inventory.md`
- **FA merge advice**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--todo_qctodo_merge_business_chain_advice.md`
- **4-agent loss audit worklog**：`docs/worklogs/2026-05-09--4_agent_loss_audit_and_5_actions.md`
- **QCTODO archived**：`docs/archive/2026-05-09--qctodo_sprint_n0_n5_archive.md`

### Spec / Amendment
- **W-AUDIT-8a spec**：`docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`（commit `c13c811e`）
- **AMD-2026-05-09-02**（5 P0-DECISION-AUDIT closure）：`docs/governance_dev/amendments/2026-05-09--operator_decision_audit_closure.md`
- **AMD-2026-05-09-03**（Graduated Canary Default）：`docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md`（commit `b1891023`）
- **AMD-2026-05-15-01**（Canary Rebase Replay Preflight + Demo Micro-Canary）：`docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`
- **AMD-2026-05-15-02 v0.7**（EDGE-P2-3 Phase 1b Close-Maker-First + Runtime Activation Layer + W-AUDIT-8b tombstone clause）：`docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`
- **EDGE-P2-3 Phase 1b spec v1.3**：`docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`
- **V094 hybrid schema migration spec**：`docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`
- **Round 1 Closure Archive**：`docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`
- **W-AUDIT-8b Funding Skew Directional spec v0.4 tombstone**：`docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md`
- **v56 P0 Engine HaltSession TTL spec**：`docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md`（~600-1000 LOC，PA drafting，ETA 2-3h from 2026-05-19 20:30 UTC）
- **ADR-0015** openclaw_core sunset / **ADR-0017** scanner authority retirement / **ADR-0018** funding_arb retire / **ADR-0020** Layer 2 manual+supervisor-only / **ADR-0022** strategist cap / **ADR-0023** SourceAvailability schema

### Close-Maker-First 3-agent Verdicts（2026-05-15 round 1 — Spec）
- **PM verdict**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--close_maker_first_pm_verdict.md`
- **PA verdict + spec outline**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--close_maker_first_pa_verdict.md`
- **FA verdict + AC**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--close_maker_first_fa_verdict.md`

### Close-Maker-First 4-agent AMD Adversarial Review（2026-05-15 round 2 — AMD）
- **QC**：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_qc.md`
- **FA round 2**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_fa.md`
- **BB**：`docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_bb.md`
- **MIT**：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_mit.md`
- **Consolidated 4-agent summary**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_consolidated.md`

### v56 P0 incident
- **E2 RCA verdict**：`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-19--engine_watchdog_respawn_loop_and_trading_inert_rca.md`
- **PA spec（drafting）**：`docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md`

### Adversarial Verification
- **v3 PM Sign-off summary**：`2026-05-09--audit_fix_verification_v3_summary.md`
- **v2 PM Sign-off summary**：`2026-05-09--audit_fix_verification_v2_summary.md`
- **v1 PM Sign-off summary**：`2026-05-09--audit_fix_verification_summary.md`
- **PA Fix Plan v2（DUAL-TRACK）**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md`
- **2026-05-08 12-Agent Full Audit + PA Fix Plan**：`2026-05-08--full_audit_fix_plan.md`
- **Verified-closed archives**：`docs/archive/2026-05-09--w_audit_verified_closed_archive_{,v2,v3}.md`

### Bybit / API
- **Bybit API 字典/審計**：`docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`

### Process
- **Operator G3-08 enable evidence**：commit `dddc5dc1` restart_all.sh wire + 2026-05-09 17:27 UTC engine.log `cost_edge_advisor spawned env=1 phase=B_shadow`

### v55 翻譯歸檔
- **歷史 ✅ DONE 詳情**：`docs/archive/2026-05-19--todo_v55_translation_archive.md`（本次同步建立，收納 v37-v55 之 carry-forward 全文 + §11 / §12 已完成 commit chain）
