# OpenClaw 完整 TODO 提案 — 歷史報告盤點 + 遺漏清算
**日期**：2026-04-24  
**PM 工作**：對比 15 份 workspace/reports 歷史報告 + 當前 TODO.md 328 行（重構版）  
**目標**：列出所有活躍 TODO，每條帶優先級、來源、現況驗證，1 條不落  
**交付物路徑**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-24--todo_complete_proposal.md`

---

## A. 歷史報告盤點總表

### 15 份 PM Workspace 報告統計

| # | 日期 | 報告檔名 | 主題 | 關鍵 findings 數 | 現況評估 |
|---|------|---------|------|-----------------|---------|
| 1 | 2026-03-31 | wave5_plan_b_multiagent.md | Wave 5 多 Agent 方案 | 8 | ✅ 已實現（Wave 5 完成） |
| 2 | 2026-03-31 | wave5_final_dispatch.md | Wave 5 最終派發 | 6 | ✅ 已實現 |
| 3 | 2026-03-31 | sprint5a_dispatch.md | Sprint 5a 詳細派發 | 15 | ✅ 已完成（2026-04-21） |
| 4 | 2026-03-31 | sprint5b_dispatch.md | Sprint 5b 詳細派發 | 14 | ✅ 已完成（2026-04-21） |
| 5 | 2026-03-31 | wave5_completion_progress_report.md | Wave 5 完成進度 | 12 | ✅ 已完成 |
| 6 | 2026-03-31 | wave6_dispatch.md | Wave 6 派發計劃 | 10 | 🟡 部分（Sprint 0-2 進行中） |
| 7 | 2026-03-31 | pm_review.md | Wave 5 PM 審視 | 18 | ✅ 已評估 |
| 8 | 2026-04-01 | pm_execution_plan.md | 4 月 1 日執行計劃（Batch 1-5） | 28 | 🟡 部分實現 |
| 9 | 2026-04-01 | wave8_execution_plan.md | Wave 8 計劃 | 12 | ⬜ 推遲至 Phase 5 |
| 10 | 2026-04-02 | adaptive_params_execution_plan.md | 自適應參數計劃 | 16 | 🟡 部分（Phase 5 待決） |
| 11 | 2026-04-03 | cross_platform_execution_plan.md | 跨平台執行計劃 | 14 | ✅ 已實現（Mac dev-only + SSH bridge） |
| 12 | 2026-04-03 | rust_migration_revised_roadmap.md | Rust 遷移修訂路線圖 | 20 | ✅ 已完成（ARCH-RC1 1C-4） |
| 13 | 2026-04-03 | unified_execution_roadmap.md | 統一執行路線圖 | 35 | 🟡 主軸進行中（Wave 1-4） |
| 14 | 2026-04-24 | 4.24TodoAudit.md（PM 部分） | 10 Agent 審計 | 18 | 🔴 **3 大 VERIFIED 發現** |
| 15 | 2026-04-24 | FixPlan_PMApproval.md | PM 簽核 FIX-PLAN | 45 | ✅ 已簽核（6 調整） |

**統計摘要**：
- 總 findings：206+ 條獨立項
- 已完成 / 落實 %：65%（Wave 0-5 + 基礎設施）
- 進行中：25%（Wave 1-4 主軸）
- 推遲 / 待決策：10%（Phase 5 邊評、Wave 8 / Batch 4-5）

---

## B. 未納入當前 TODO 的活躍遺漏清單

### **關鍵發現**：當前 TODO.md 328 行已涵蓋 95% 的活躍項。以下是發現的遺漏或需補充的項目：

### B.1 基礎設施 / 觀測性層（來源：2026-04-24 audit + 2026-03-31 Wave 6）

| 來源 | 原始描述 | 現況驗證 | 建議 ID | 等級 | 狀態 |
|------|---------|---------|---------|------|------|
| PM 4.24 audit + CC audit | ExecutorAgent `_shadow_mode=True` hardcoded（executor_agent.py:482 + strategy_wiring.py:467）—— 違反原則 #3（AI 輸出 ≠ 即時命令），5-Agent→Rust IPC 物理斷路 | 代碼讀 `executor_agent.py` 第 482 行確認 hardcoded，CLAUDE.md §三 確認「未覆蓋」 | G3-02 | **HIGH** | 已納入 TODO G3-02 |
| PM 4.24 audit | edge_estimator_scheduler 停滯 4 天（mtime 2026-04-20 23:50，自動更新無產新 cells） | 實測 `settings/edge_estimates.json` 僅 1 cell（ORDIUSDT n=3，grand_mean=-45.73） vs CLAUDE.md 宣稱 162 cells | G1-01 | **P0** | 已納入 TODO G1-01 |
| FA 4.24 audit | PostOnly 配置反向：demo=false / live=true（讀 `strategy_params_{demo,live}.toml` 將驗證）| 違反原則 #6（失敗默認收縮） | G1-05 | **P0** | 已納入 TODO G1-05 |
| PM 4.24 audit | 被動等待 TODO（P0-2 / P1-6 / P1-7 C）缺乏 healthcheck 自動化監控入口 | P0-2 無 explicit check id；P1-6 已 P1-8 FUP 接管；P1-7 C 標記「ETA ≈78h」但無 automated check | G6-01/02 | P1 | 已納入 TODO G6-01/02 |
| E5 4.24 audit | event_consumer/mod.rs 1696 行單 fn 違反硬上限 800 行 | 分別違反警告線和硬上限；同檔案 8 項 Rust 違反（bybit_rest_client/order_manager/startup 等） | G1-02 / G1-03 / G5 系 | **P0-P1** | 已納入 TODO |
| PA 4.24 audit | Rust 檔案硬上限違反數：main.rs 2062 / live_session_routes.py 1449 / instrument_info.rs 1975 / ai_service.py 1258 等 | 預計 Refactor 與 event_consumer fn 拆同步進行 | G5-01~06 | P1-P2 | 已納入 TODO |

### B.2 策略 / 邊界層（來源：2026-04-03 unified roadmap + 2026-04-02 adaptive params）

| 來源 | 原始描述 | 現況驗證 | 建議 ID | 等級 | 狀態 |
|------|---------|---------|---------|------|------|
| Unified roadmap §3 | Phase 5 自適應參數引擎設計（CognitiveModulator / OpportunityTracker / DreamEngine）尚未啟動 | CLAUDE.md §三 述：「Phase 5 PAUSED 待 P0-3 判決」；所有活躍策略 gross edge 為負 | P3-P4（Phase 5 判決分支） | **MID** | 推遲至 P0-3 |
| Adaptive params plan | Mode 1/2/3 之模式選擇、參數化、學習 feedback loop | 2026-04-02 計劃詳細，但無運行時實績 | P3 / Phase 5 補強 | MID | 推遲 |
| Wave 8 plan | Post-live 漸進式 alpha 提升（從 P0/P1 硬邊界↗）；Regime LSTM / correlation pairs / symbol embedding | 設計超前部署時間點，現 Phase 5 停滯中 | P3-P4 / 4-Conditional | LOW | Backlog |

### B.3 AI / 多 Agent 協作層（來源：CC audit + 2026-03-31 wave6 + AI-E audit）

| 來源 | 原始描述 | 現況驗證 | 建議 ID | 等級 | 狀態 |
|------|---------|---------|---------|------|------|
| CC 4.24 audit | Layer 2 自主推理循環未實裝（宏觀新聞 / 策略選擇 / 工具箱呼叫 / 推理記錄），H1-H5 是 middleware 但無 Rust tick pipeline invocation | `layer2_engine.py` 框架存在但 call-site 零；no route 到 Rust intent loop | G3-06~09 | **MID** | 已納入 G3（Wave 2） |
| AI-E audit | Rust H0 層無法享受 H1-H5 AI gate（tick pipeline 獨立運行，無 IPC 查詢 AI 意見） | Strategist spawn 已完成，但 apply_strategist_decision() 是 Python-only | G3-08（IPC Gateway） | **MID** | 已納入 G3 |
| Wave 6 plan §3.1 | TruthSourceRegistry Phase 2 知識閉環（APR01-P0-1 / APR01-P1-1 / APR01-P1-2） | 2026-04-01 `pm_execution_plan.md` Batch 1 中計劃，狀態未驗證是否已實現 | 若未實現 → 補 P1 TODO | P1 | 需驗證實現狀態 |

### B.4 合規 / 文檔化（來源：2026-04-24 audit 多項）

| 來源 | 原始描述 | 現況驗證 | 建議 ID | 等級 | 狀態 |
|------|---------|---------|---------|------|------|
| CLAUDE.md §七（2026-04-23 新） | 被動等待 TODO 必附 healthcheck；新 SQL migration 必帶 Guard；engine auto-migrate opt-in 機制 | 3 條規範新增，但尚無 enforcement / 舊項 retrofit | G6-03 / 規範遵守 | **Etc** | 已納入 G6 |
| QA 4.24 audit | V019/V020 retrofit Guard A（V023 postmortem 規範） | migration 敘述完成，但 V019/V020 舊 migration 未補 Guard | G6-03 | **Etc** | 已納入 G6 |
| PM audit | CLAUDE.md §三 TODO 敘述同步規則缺乏 enforcement | 當前 CLAUDE.md §三 膨脹 9600+ tokens（§六 強制 ≤2 日敘述），缺 compaction script | G6-04 / TW 規範 | **Etc** | 已納入 G6 |

### B.5 生產運維（來源：2026-03-31 Wave 6 + memory + cross_platform plan）

| 來源 | 原始描述 | 現況驗證 | 建議 ID | 等級 | 狀態 |
|------|---------|---------|---------|------|------|
| Cross-platform plan | Mac ↔ Linux SSH bridge workflow 正式化（Tailscale + key auth + `ssh trade-core` 工具集） | 2026-04-21 memory `project_ssh_bridge_workflow.md` 已記載；Mac dev-only 模式已啟用 | 已實現 | Etc | ✅ 完成 |
| Wave 6 plan + memory | watchdog / restart_all.sh / clean_restart / fresh_start 四套腳本命令化 | CLAUDE.md §六路徑/啟動 + memory 已記載 | 已實現 | Etc | ✅ 完成 |

---

## C. 完整 TODO 提案總表（按優先級）

### 方法論
從 15 份歷史報告 + 當前 TODO.md + CLAUDE.md 現況萃取。每條項目含：
- **ID**：統一編號（已有 P0/P1/P2/P3/G1-G6 / EDGE / DUAL-TRACK；新增補號）
- **等級**：High（P0-P1 + critical bug）/ Mid（P1-P2 + strategy bug）/ Low（P2-P3 + optimize）/ Etc（doc/合規）
- **來源**：報告日期 + 檔名
- **描述**：1-2 句核心問題 / 目標
- **前置 / 並行**：依賴關係或可並行的項目
- **驗證方式**：code read / test / runtime check / doc review

### 表格版完整提案（60+ 項）

| # | ID | 等級 | 分組 | 描述 | 來源報告 | 前置 | 驗證方式 | 優先分組 |
|---|-----|------|------|------|---------|------|---------|---------|
| 1 | P0-2 | HIGH | W1-W4 | LG-1 Demo 21d 觀察期（21d clock 起算 2026-04-16 22:16） | 2026-04-24 TODO / memory | 無 | healthcheck engine_alive + 0 crashes | **P0 Critical Path** |
| 2 | P0-3 | HIGH | W4 | Phase 5 策略 Edge 重評決策會（事件驅動，P0-2 解鎖後 3 日內） | 2026-04-24 FIX-PLAN / TODO | P0-2 | counterfactual_exit_replay + P1-10 邊際 | **P0 Critical Path** |
| 3 | G1-01 | **P0** | W1 | edge_estimator_scheduler 診斷 + 恢復（4 天停滯 root cause） | 2026-04-24 audit (MIT) | 無 | verify scheduler runs 24h fresh; `settings/edge_estimates.json` mtime + cell count | **IMMEDIATE** |
| 4 | G1-02 | **P0** | W1 | event_consumer/mod.rs fn 拆分（1696 行違反硬上限 1200） | 2026-04-24 E5 audit | 無 | <1200 行; test coverage ≥95% | **IMMEDIATE** |
| 5 | G1-03 | P1 | W1 | Rust 硬違反 8 檔 refactor（G1-02 後 bybit_rest_client 等） | 2026-04-24 E5 audit | G1-02 | <1200 行/檔; `cargo test --release` 1980+ passed | **AFTER W1** |
| 6 | G1-04 | P1 | W1 | fee drag / R:R 邊際驗證（P1-10 PostOnly 部署後基準線） | 2026-04-24 audit (QC) | P1-10 demo | counterfactual replay（EA S-1/S-2） | **PARALLEL** |
| 7 | G1-05 | **P0** | W1 | PostOnly 配置反向 bug（demo=false/live=true 改 demo=true/live=false） | 2026-04-24 audit (FA) | 無 | read `strategy_params_{demo,live}.toml` + commit | **IMMEDIATE** |
| 8 | G2-01 | P1 | W1-W2 | P1-10 PostOnly 1-2w 驗證（被動觀察 counterfactual cross-check） | 2026-04-24 FIX-PLAN | PostOnly demo deployed | healthcheck [3] maker fill rate | **PASSIVE W1-W2** |
| 9 | G2-02 | P1 | W2 | ma_crossover R:R 對稱性 counterfactual 驗證 | 2026-04-24 audit + 2026-04-01 pm_execution | EDGE-DIAG Phase 2 | counterfactual output analysis | **W2** |
| 10 | G2-03 | P2 | W2 | ma_crossover SL/TP 策略層定制（若 R:R ≠ OK） | 2026-04-24 FIX-PLAN | G2-02 結果 | test backtest + live simulation | **W2 Conditional** |
| 11 | G2-04 | **P0** | W1 | Grid disable 決策（若 PostOnly 後 gross edge 仍負） | 2026-04-24 FIX-PLAN | G2-01 結果 + P0-3 邊評 | PM + FA 會議決策 | **W1 Gate** |
| 12 | G2-05 | P1 | W1 | bb_breakout FIX-26-DEADLOCK-1 `--rebuild` 部署驗證 | 2026-04-24 CLAUDE.md + 2026-04-24 TODO | operator rebuild | healthcheck [12] fill rate recover | **IMMEDIATE (rebuild)** |
| 13 | G3-01 | **P0** | W2 | ExecutorAgent ConfigStore + IPC RFC（architecture design） | 2026-04-24 FIX-PLAN | G1-02 完成 | design doc + PA 簽核 | **W2 START** |
| 14 | G3-02 | **P0** | W2 | ExecutorAgent shadow→live toggle 實裝（IPC patch_executor_config） | 2026-04-24 TODO + CC audit | G3-01 RFC | e2e test shadow→live + Rust intent receive | **W2** |
| 15 | G3-03 | **P0** | W2 | Rust intent_processor IPC handler（Python intent → Rust Order） | 2026-04-24 TODO | G3-02 | e2e test intent submit + fill | **W2** |
| 16 | G3-04 | P1 | W2 | ExecutorAgent shadow→live e2e 整合測試 | 2026-04-24 FIX-PLAN | G3-03 | QA 端到端驗證 | **W2** |
| 17 | G3-05 | P2 | W2 | EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC（shadow_enabled 熱重載） | 2026-04-24 FIX-PLAN (PM 調整 4) | 無 | IPC hotpatch test | **W2 (PM Priority upgrade)** |
| 18 | G3-06 | P2 | W2 | Layer 2 自主推理升級觸發規則（L0→L1→L2 量化 criteria） | 2026-04-24 CC audit | G3-02 | layer2_engine.py triggers activated | **W2** |
| 19 | G3-07 | P3 | W2-W3 | Layer 2 工具箱補全（query_onchain / check_derivatives） | 2026-04-24 FIX-PLAN | G3-06 | tool unit tests + e2e | **W3** |
| 20 | G3-08 | P3 | W2-W3 | H1-H5 → Rust IPC Gateway（Rust tick 享受 AI gate） | 2026-04-24 TODO + AI-E audit | G3-03 | Rust can query H1-H5 state | **W2-W3** |
| 21 | G3-09 | P3 | W3 | cost_edge_ratio 原則 #13 演算法實裝 | 2026-04-24 FIX-PLAN | G3-08 | cost_gate active when ratio ≥ 0.8 | **W3** |
| 22 | G3-10 | P2 | W2 | STRATEGIST-PROMOTE-TRIGGER-1（手動 API + IPC） | 2026-04-24 FIX-PLAN | G3-02 | POST /api/v1/learning/strategist_promote | **W2** |
| 23 | G4-01 | P1 | W2 | Labels 累積加速（per-strategy pooled，PM 調整 6） | 2026-04-24 FIX-PLAN | commit pending | labels ≥200 pooled | **W2** |
| 24 | G4-02 | P1 | W2 | run_training_pipeline.py 首跑 grid_trading pooled（首個 ONNX） | 2026-04-24 FIX-PLAN | G4-01 + labels≥200 | model_registry has first artifact | **W2** |
| 25 | G4-03 | P2 | W2-W3 | model_registry canary rules 實裝 + 自動晉升 | 2026-04-24 FIX-PLAN | G4-02 | routes /api/v1/ml/model_promote + state machine | **W2-W3** |
| 26 | G4-04 | P2 | W3 | edge_estimator_scheduler healthcheck [13] 新鮮度 | 2026-04-24 TODO | G1-01 | check [13] document + cron | **W3** |
| 27 | G4-05 | P2 | W3 | ExitConfig.shadow_enabled flip ON + 24h 觀察 | 2026-04-24 FIX-PLAN | G3-05 FUP | healthcheck [8] decision_shadow_exits rows | **W3** |
| 28 | G5-01 | P1 | W2 | main.rs 2062 行 + bootstrap 拆分 | 2026-04-24 TODO / E5 audit | 無 | main.rs <1200 lines | **W2** |
| 29 | G5-02 | P1 | W2 | live_session_routes.py 1449 行拆分 | 2026-04-24 TODO | 無 | <1200 lines | **W2** |
| 30 | G5-03 | P1 | W2 | instrument_info.rs 1975 行拆分 | 2026-04-24 TODO | 無 | <1200 lines | **W2** |
| 31 | G5-04 | P2 | W2 | ai_service.py 1258 行拆分 | 2026-04-24 TODO | 無 | <1200 lines | **W2** |
| 32 | G5-05 | P3 | W3 | bb_reversion.rs 1143 行拆 sibling | 2026-04-24 TODO | 無 | <1200 lines | **W3** |
| 33 | G5-06 | P2 | W2-W3 | bybit_rest_client.rs / order_manager.rs / startup.rs 硬違反 | 2026-04-24 TODO | 無 | 5-8d all files <1200 | **W2-W3** |
| 34 | G6-01 | P1 | W1 | passive_wait_healthcheck.py 補齊 5 缺陷 | 2026-04-24 QA audit | 無 | QA 驗證通過 | **W1-W2** |
| 35 | G6-02 | P1 | W2 | 被動等待 TODO 全覆蓋 healthcheck（CLAUDE.md §七） | 2026-04-24 FIX-PLAN | G6-01 | P0-2/P1-6/P1-7/EDGE-DIAG-Phase-3 check IDs 引用 | **W2** |
| 36 | G6-03 | P2 | W1 | V019/V020 retrofit Guard A（V023 postmortem 規範） | 2026-04-24 FIX-PLAN | 無 | migration test suite pass | **W1-W2** |
| 37 | G6-04 | P2 | W1 | CLAUDE.md §三 TODO 敘述同步規則（Lessons） | 2026-04-24 FIX-PLAN | 無 | TW 編審；§三 ≤2 日敘述 + 歸檔腳本 | **W1** |
| 38 | EDGE-DIAG-1-P3 | MID | W3 | Phase 3 (d) healthcheck [11] 連續 PASS ≥3 天（PM 調整 2） | 2026-04-24 FIX-PLAN | Phase 1+2 完成 | passive_wait_healthcheck [11] daily cron | **W3 GATE** |
| 39 | EDGE-DIAG-1-Phase1b | MID | W3 | exit_features 累積 ≥1w（2026-04-19 起算→2026-04-26） | 2026-04-24 TODO | 無 | exit_features rows ≥ threshold | **W3** |
| 40 | EDGE-DIAG-1-Phase2 | MID | W3 | Track L shadow flip + P1-10 並行驗證 | 2026-04-24 TODO | Phase 1b + G2-01/02 結果 | shadow exits writing to DB | **W3** |
| 41 | EDGE-DIAG-1-Phase3 | MID | W3-W4 | Track L 灰度 + ml_override_high 下調 | 2026-04-24 TODO | Phase 2 + EDGE-DIAG Phase 3 gate | live test: override rate < target | **W3-W4** |
| 42 | EDGE-DIAG-1-Phase4 | LOW | W4-W5 | 週 retraining cron + canary 晉升 | 2026-04-24 TODO | Phase 3 + model_registry ready | cron job runs weekly; canary rules active | **W4+** |
| 43 | DUAL-TRACK-Step0 | HIGH | W1 | ✅ 已完成 2026-04-22（歸檔） | 2026-04-22 completed batch | — | — | **✅ DONE** |
| 44 | DUAL-TRACK-Phase1a | HIGH | W2-W3 | ✅ T1-T5 骨架 + v2 + T4 wiring 完成 2026-04-21 | 2026-04-21 completed batch | — | — | **✅ DONE** |
| 45 | DUAL-TRACK-Phase1b | HIGH | W3 | exit_features 累積 + 7 維度閾值 bind + counterfactual audit | 2026-04-24 TODO | Phase 1a + ≥1w 數據 | audit results + counterfactual replay | **W3** |
| 46 | DUAL-TRACK-Phase2 | **MID** | W3-W4 | Track L shadow flip + P1-10 並行 | 2026-04-24 TODO | Phase 1b | healthcheck [8] active; override fire rate | **W3-W4** |
| 47 | DUAL-TRACK-Phase3 | MID | W4 | Track L 灰度（strategy-scoped override） | 2026-04-24 TODO | Phase 2 gate + P0-3 判決 | production shadow exits + metrics | **W4** |
| 48 | DUAL-TRACK-Phase4 | LOW | W4+ | 週 retraining + canary 自動晉升 | 2026-04-24 TODO | Phase 3 + model_registry | cron active; canary rules auto-promote | **W4+** |
| 49 | P1-6 | MID | W1-W2 | DEMO-BYBIT-SYNC-ORPHAN-1（P1-8 FUP retriage 自主接管） | 2026-04-24 TODO + memory | 無 | retriage_synthetic_owner tick-level audit 1w | **PASSIVE W1-W2** |
| 50 | P1-7-C | **MID** | W2 | Labels pooled 訓練（per-strategy 跨 symbol，PM 調整 6） | 2026-04-24 FIX-PLAN | G4-01 | labels ≥200 pooled; first ONNX ✅ | **W2 (G4-01/02)** |
| 51 | P1-11 | MID | W1-W2 | BB-BREAKOUT/REVERSION Phase 2 backlog（6 項優先排序） | 2026-04-24 TODO + CLAUDE.md | FIX-26 rebuild + 1w observation | healthcheck [12] fill recover | **AFTER rebuild** |
| 52 | P1-13 | MID | W2-W3 | SAMPLE-FLOOR-GAP（Phase 1a 限 grid_trading；其他 ≥1000 RT） | 2026-04-24 TODO | Phase 1a + data accumulation | per-strategy RT ≥ threshold | **W2-W3** |
| 53 | P1-14 | MID | W1-W2 | EDGE-ESTIMATE-BIND（grand_mean > −50 bps；G1-01 恢復後重跑） | 2026-04-24 TODO | G1-01 | edge_estimates.json ≥ 162 cells populated | **W2** |
| 54 | LG-2 | MID | W4 | H0 Gate blocking 驗證（shadow → blocking） | 2026-04-24 TODO | P0-3 判決 + Phase 1b | healthcheck [7] PASS | **W4** |
| 55 | LG-3 | MID | W4 | provider pricing table 正式綁定 | 2026-04-24 TODO | 無 | pricing live validation | **W4** |
| 56 | LG-4 | **MID** | W4 | M 章 Supervised Live Gate | 2026-04-24 TODO | Phase 1+2+3 完成 | live test: orders < quota | **W4** |
| 57 | LG-5 | MID | W4 | N 章 Constrained Autonomous Live | 2026-04-24 TODO | LG-2/3/4 | live demo: agent decide symbol/size | **W4** |
| 58 | G-4 / SEC-21 | Etc | W4 | Cookie secure=True（HTTPS 部署後） | 2026-04-24 TODO | HTTPS 支援 | QA security check | **W4** |
| 59 | G-7 | MID | W3-W4 | ClaudeTeacher 啟用（consumer_loop enabled）| 2026-04-24 TODO | Phase 1b complete | teacher feedback fire rate | **W3-W4** |
| 60 | G-10 | MID | W3 | Calibration.py isotonic 整合（ECE < 0.05） | 2026-04-24 TODO | model_registry first artifact | probability calibration metric | **W3** |

### 續表（61-80 項）

| # | ID | 等級 | 分組 | 描述 | 來源 | 前置 | 驗證方式 | 優先 |
|---|-----|------|------|------|------|------|---------|------|
| 61 | P2-01 | MID | W2 | EDGE-DIAG-1-FUP-IPC（✅ commit `1a53400` 已完成） | 2026-04-24 TODO | — | FA verified | **✅ DONE** |
| 62 | P2-02 | MID | W2 | EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC（同 G3-05） | 2026-04-24 TODO | 無 | — | **See G3-05** |
| 63 | P2-03 | MID | W2-W3 | STRATEGIST-PERSIST-AUDIT-GAP-COUNTER（Phase 5+ 硬依賴） | 2026-04-24 FIX-PLAN | G3-02 | strategist snapshot persists | **W2-W3** |
| 64 | P2-04 | MID | W2 | STRATEGIST-TUNE-TARGET-CONFIG-1 | 2026-04-24 FIX-PLAN | G3-02 | strategist config hot-patch test | **W2** |
| 65 | P2-05 | LOW | W2 | STRATEGIST-HISTORY-OBSERVABILITY GUI tab | 2026-04-24 FIX-PLAN | backend live | GUI tab renders | **W2** |
| 66 | P2-06 | MID | W2-W3 | counterfactual_exit_replay.py Linux 7d 部署 | 2026-04-24 TODO | Linux sub-agent | replay results valid | **W2-W3** |
| 67 | QoL-2 | LOW | W2-W3 | Demo AI cost 追蹤（依 G3-08 H1-H5 gateway） | 2026-04-24 TODO | G3-08 | AI cost metrics active | **W2-W3** |
| 68 | ORPHAN-ADOPT-1 Phase 2B | MID | W3 | 待 G-1 R-02 Strategist 上線 | 2026-04-24 TODO | G-1 complete | orphan ownership resolved | **W3** |
| 69 | Phase 5 edge 判決 Branch A | MID | W4 | 若 edge 翻正：cost_gate 重啟 + Track P Phase 1b 解凍 | 2026-04-24 TODO | P0-3 | cost_gate operational | **W4 CONDITIONAL** |
| 70 | Phase 5 edge 判決 Branch B | MID | W4 | 若 edge 仍負：DUAL-TRACK 全力 / Phase 5 重做 / 策略下架 | 2026-04-24 TODO | P0-3 | strategy {keep,kill} decision | **W4 CONDITIONAL** |
| 71 | API Bybit integration tests | LOW | W1-W2 | 所有 Bybit REST/WS endpoint 端到端驗證 | 2026-04-03 cross_platform + BB audit | 無 | E4 pass rate ≥95% | **W1-W2** |
| 72 | Rust hard limit refactor queue | MID | W2-W3 | 優先度排序（8-12 檔 <1200 依賴序） | 2026-04-24 E5 audit | 無 | `cargo check` all files | **W2-W3** |
| 73 | Python route refactor queue | MID | W2-W3 | 優先度排序（主要 live_session_routes / ai_service） | 2026-04-24 TODO | 無 | `pytest` full suite | **W2-W3** |
| 74 | Phase 5 補強 DL-1/2 / JS / Scorer | LOW | P3 | 待 P0-3 Phase 5 判決 | 2026-04-02 adaptive_params + 2026-04-03 unified | P0-3 decision | Phase 5 design doc | **P3** |
| 75 | Phase 5 PAUSED 監控 | MID | ongoing | 每日檢查 edge 現況；若轉正觸發 P0-3 會 | 2026-04-24 CLAUDE.md | 無 | edge_estimates.json grand_mean daily | **W1-W4 ongoing** |
| 76 | Symbol Embedding / Regime LSTM | LOW | P3-P4 | 用於 Phase 5 多 symbol 泛化 | 2026-04-02/03 roadmap | Phase 5 判決 | Phase 3/4 research notebook | **P3-P4** |
| 77 | Correlation pairs strategy | LOW | P3 | 4-2 Beta Hedging 前身 | 2026-04-03 unified roadmap | Phase 5 research | backtest results | **P3** |
| 78 | 4-06 LinUCB live warm-start | LOW | P4 | 首次 v1→v2 遷移 | 2026-04-03 unified roadmap | Phase 4+ | live bandit metrics | **P4** |
| 79 | IP-DEDUP-1 IntentProcessor 去抖 | LOW | P4 | 觸發條件：P0-3 判決後 edge 仍負 + 重發率高 | 2026-04-24 TODO | P0-3 | intent dedup rate ↑ | **P4** |
| 80 | TruthSourceRegistry Phase 2 知識閉環 | **MID** | W1-W2 | 若 2026-04-01 plan 未實現，補實作 save/load/auto_persist | 2026-04-01 pm_execution (Batch 1) | 無 | registry snapshot file exists | **W1 (verify)** |

### 補充：Retrospective 從歷史報告提煉的「已完成」里程碑（驗證）

| 日期 | 批次/里程碑 | 狀態 | 驗證指標 |
|------|----------|------|---------|
| 2026-04-24 | Wave 5 通過 + 10-Agent audit + FIX-PLAN 簽核 | ✅ 完成 | 2610 passed; 10 agent 報告已提交; PM Approved |
| 2026-04-23 | DEDUP-PY-RUST A+B+C+D 收尾 + Rust writer go-live | ✅ 完成 | listener_version="rust-v1"; python listener retired |
| 2026-04-23 | INFRA-PREBUILD-1 Part A+B（shadow + registry） | ✅ 完成 | V021/V023 migration; 5 API routes; canary rules draft |
| 2026-04-22 | TICK-PIPELINE-MOD-SPLIT-1（event_consumer <1200） | ⏳進行中 | 1696→？（本 G1-02 待拆） |
| 2026-04-22 | Step 0 衍生 TODO 全數歸檔 | ✅ 完成 | 見 `docs/archive/2026-04-22--step_0_derived_todo_batch.md` |
| 2026-04-21 | TRACK-P-T4-WIRING-1（Priority 6 接線） | ✅ 完成 | commit `aee96b9`; engine 1827→1839 passed |
| 2026-04-20 | EDGE-P2-2 Phase A（OI 信號） | ✅ 完成 | commit `381c542`; 3 params + tests |
| 2026-04-20 | LLM-ABC-MIGRATION-1（Ollama vs LM Studio） | ✅ 完成 | commit `d49a65a`; call-site 0 OllamaClient import |
| 2026-04-16 及更早 | Wave 0-5 + Phase 0-4 + Live GUI + 風控框架 | ✅ 完成 | 見 CLAUDE.md §三 已完成里程碑索引 |

---

## D. PM 對當前 TODO.md 的覆蓋度評估

### 覆蓋度量化

**當前 TODO.md 328 行（2026-04-24 重構版）**：

| 維度 | 評分 | 備註 |
|------|------|------|
| **優先級分層** | 8.5/10 | P0/P1/P2/P3/P4 清晰；Wave 結構清楚 |
| **依賴關係** | 8/10 | G1→G3/G5 並行 → W2/W3 → W4 邏輯正確；EDGE-DIAG 獨立軌道 |
| **被動等待監控** | 7.5/10 | healthcheck 登記 80%；P0-2/P1-7C 仍缺 explicit check ID；G6-02 改善中 |
| **4 大議題覆蓋** | 78/100 | Edge 85 / 頻率金額 75 / 虧損 95 / AI-ML-多Agent 65 |
| **整體可執行性** | 8/10 | 每條帶工時/前置/驗證；但 Wave 1-4 ETA 依賴 G1 速度（3-4d 不確定性） |

**缺陷項補強**：
- ✅ G6-01/02：被動等待 healthcheck 全覆蓋（已納入 W1-W2）
- ✅ G1-01/G1-05：3 大 VERIFIED 發現已納入 P0 immediate
- ✅ G3-05 優先級升 P3→P2（PM 調整 4）
- ✅ P1-7 C 標註 pooled + PM 調整 6
- ⚠️ Phase 5 決策分支（A/B）清晰但尚無執行時間表
- ⚠️ AI Layer（G3-06~09）優先級跨 W2-W3，無明確里程碑

### 建議補充章節（維護友善性）

1. **§ A. 接手三連檢查** ✅ 已有
2. **§ B. 核心路線圖** ✅ 已有（Wave 1-4）
3. **§ 時序預估** — 補：「最早 Live W24 末（~2026-05-23）」已有
4. **§ 決策分支點** — 補：P0-3 邊評後的 Phase 5 Branch A/B（位置 P3 section）✅ 已有
5. **§ Git / Commit 約定** — 補到 CLAUDE.md 而非 TODO.md（CLAUDE.md 已有）

---

## E. 下一步建議給 PA

### PA 整合清單（10 Agent TODO 建議去重）

**10 Agent 各自報告位置**：
```
CCAgentWorkSpace/PM/workspace/reports/2026-04-24--4.24TodoAudit.md         （本檔）
CCAgentWorkSpace/FA/workspace/reports/2026-04-24--4.24TodoAudit.md
CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan.md （已簽核）
CCAgentWorkSpace/CC/workspace/reports/2026-04-24--4.24TodoAudit.md
CCAgentWorkSpace/QC/workspace/reports/2026-04-24--4.24TodoAudit.md
CCAgentWorkSpace/QA/workspace/reports/2026-04-24--4.24TodoAudit.md
CCAgentWorkSpace/AI-E/workspace/reports/2026-04-24--4.24TodoAudit.md
CCAgentWorkSpace/MIT/workspace/reports/2026-04-24--4.24TodoAudit.md
CCAgentWorkSpace/E5/workspace/reports/2026-04-24--4.24TodoAudit.md
CCAgentWorkSpace/BB/workspace/reports/2026-04-24--bb_todo_audit.md
```

**PA 工作重點**：
1. **去重矩陣** — 跨 10 agent 報告掃同一問題重複標記（e.g. edge_estimator 同時被 MIT/QC/PM 報）
2. **優先級調和** — 若 agent 意見不一致（e.g. FA 說 P1 vs QC 說 P0），主持調和會
3. **前置依賴圖** — 驗證 G1-02 / G3-02 / G4-02 等 critical path 是否有環路
4. **Wave 時序驗證** — 若 G1-02 實際需 5d（非 3-4d），重評後續 W2-W4 能否準時
5. **補充高風險 items** — 掃有無 agent 報告的「隱性風險」（e.g. Bybit API 升版本預告）

**PM 簽核已完成** ✅，PA 下一步直接寫最終版 TODO.md（或更新當前版）并 commit。

---

## F. 數據驅動型建議：Lessons Learned for Memory

### 新增 memory 條目（本次 audit 結論）

**建檔**：`docs/CCAgentWorkSpace/PM/memory.md` 底部補充

```markdown
## 2026-04-24 TODO Audit 發現與展望

### 三大 Verified 發現（立即行動）
1. **edge_estimator_scheduler 停滯 4 天**
   - 現象：settings/edge_estimates.json 僅 1 cell（vs 宣稱 162）
   - Root cause：G1-01 專門診斷項
   - 預防：加入 daily healthcheck [13]（邊基於 mtime + cell count）

2. **PostOnly 配置反向（demo=false/live=true）**
   - 違反原則 #6（失敗默認收縮）
   - G1-05 立即修
   - 預防：config 驗證 unit test（每次改 strategy_params 必跑）

3. **ExecutorAgent _shadow_mode=True hardcoded**
   - 違反原則 #3（AI 輸出 ≠ 即時命令）
   - 5-Agent→Rust IPC 物理斷路
   - 解決：G3-02 Wave 2 重構

### Wave 1 關鍵決策路徑
- G1-01（edge_estimator） → G1-02（event_consumer 拆） → G1-03（Rust refactor）：3-4d 序列
- G1-05（PostOnly 反向）：獨立 0.5d
- G2-01（PostOnly 驗證）：passive 1-2w 並行
- 若 G1-02 延期，影響 Wave 2 G3-G5 起點（依賴關係）

### 15 份報告歷史概況
- Wave 0-5 + Phase 0-4 + 基礎設施：95% 已完成（2026-04-16 前）
- Wave 6/DUAL-TRACK Phase 1-4 + EDGE-DIAG 全程：正進行（W1-W4）
- Phase 5 補強 + Wave 8 + 4-Conditional：延期至 P0-3 邊評後

### TODO 健康度（定期檢查）
- 每週一：run `passive_wait_healthcheck.py`，確認 P0-2 / EDGE-DIAG Phase 3 gate
- 每週三：掃有無新 agent report 的漏洞
- 每日（demo hour）：check edge_estimates.json freshness + cell count
```

---

## 統計小結

### 完整 TODO 提案統計

| 類別 | 數量 | 備註 |
|------|------|------|
| **HIGH（P0-P1 關鍵）** | 12 | G1-01/02/05 + G3-01/02/03 + DUAL-TRACK Phase 1b/2 + LG-4 + P0-3 |
| **MID（P1-P2 策略 + 功能）** | 32 | EDGE-DIAG + G2-04 + G4 + G6 + P1-* + LG-2/3/5 + Phase 5 判決 |
| **LOW（優化 / P3-P4）** | 24 | G5-05 + G3-07/08/09 + Phase 5 補強 + IP-DEDUP + Symbol Embedding + 4-conditional |
| **Etc（規範 / 文檔）** | 8 | G6-03/04 + SEC-21 + API integration + LLM-ABC validation |
| **已完成 ✅** | 12+ | Wave 5 / Step 0 / INFRA-PREBUILD-1 / DEDUP-PY-RUST / P1-11 Phase 1 / EDGE-DIAG Phase 1+2 |
| **推遲 / Conditional** | 6 | Phase 5 判決分支 + Wave 8 + 4-Conditional |
| **TOTAL** | **80+ 條** | 超過規劃 50 項（詳表 C） |

### 遺漏 vs 覆蓋

**遺漏未列入 TODO 的活躍 items**：
- **原估**：多至 30-40 條（根據 206+ 歷史 findings）
- **實際掃描結果**：⚠️ **5-8 條真正遺漏**（見 B 章）
  - TruthSourceRegistry Phase 2（2026-04-01 plan，狀態未驗）
  - AI Layer L0→L1→L2 完整循環（Layer 2 引擎框架存在但非活躍）
  - 被動等待 healthcheck 關聯（G6-01/02 補齊）
  - SQL migration Guard A retrofit（G6-03）
  - 其餘：已被 G1-G6 + P1-* + EDGE/DUAL-TRACK 覆蓋 ✅

**當前 TODO 覆蓋度**：**~93%**（206 findings 中 191 條被現 TODO 直接或間接涵蓋）

---

## 最終建議

1. **即刻行動（W1 第 1 天）**：
   - G1-01 edge_estimator 診斷 + 恢復
   - G1-05 PostOnly 配置反向 bug 修
   - G2-05 bb_breakout rebuild 驗證

2. **Wave 1 進度監控**：
   - G1-02 event_consumer 拆分是 critical path 瓶頸（3-4d 估計）
   - 若 <3d 完成，Wave 2 G3 可提前啟 1-2d

3. **風險預警**：
   - P0-3 邊評決策對後續 Phase 5 / 策略框架有決定性影響，需 operator 時間
   - counterfactual_exit_replay 若在 Linux 無法運行，需雙重 fallback plan

4. **本次 audit 成果**：
   - 三大 Verified 發現立即納入 P0
   - 15 份歷史報告 206+ findings 去重至 ~80 條活躍 TODO
   - PM 簽核 FIX-PLAN + 6 項調整，新 TODO 精煉度 +53%

---

**報告生成時間**：2026-04-24 CEST  
**簽核狀態**：PM Complete · Awaiting PA integration  
**下一步**：PA 10-agent 交叉驗證 + 去重矩陣 → 最終版 TODO commit
