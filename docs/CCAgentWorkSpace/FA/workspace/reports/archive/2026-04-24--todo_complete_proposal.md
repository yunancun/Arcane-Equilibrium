# FA 完整 TODO 提案報告
# FA Complete TODO Proposal — OpenClaw 2026-04-24

**日期**: 2026-04-24 CEST  
**審計員**: FA (Functional Auditor)  
**基準版本**: TODO.md 10-Agent Audit 重構版（328 行）  
**評估方式**: 遍歷 9 份 FA 歷史報告 (2026-03-31 ~ 2026-04-24) + memory.md 記載  
**輸出目標**: 列出所有「遺漏未入當前 TODO」的 FA 活躍項，按等級分類

---

## 一、FA 9 份歷史報告盤點

| 日期 | 報告 | FA Findings 數 | 仍活躍條目 | 狀態 |
|------|------|--------|---------|------|
| 2026-03-31 | wave5_functional_acceptance.md | 5 B-MVP 驗收 | 4/5 通過 | ✅ |
| 2026-03-31 | wave5_gap_analysis.md | 2 BLOCKER (G-01, G-05) | 0（Wave 5a 修復） | ✅ |
| 2026-04-01 | functional_gap_audit.md | 17 P0/P1/P2/P3 + 5 死代碼 | 6 活躍（TruthRegistry / MessageBus / BacktestEngine 等） | 🟡 |
| 2026-04-02 | adaptive_params_functional_spec.md | 6 參數適應項 (ATR/成本/Regime) | 全 6 項未入 Wave 1 TODO | 🔴 |
| 2026-04-03 | cross_platform_functional_spec.md | XP-1~4 跨平台 4 項 | 3 項(路徑/LLM/部署) 未完成 | 🟡 |
| 2026-04-03 | improvement_report_gap_comparison.md | 報告 vs 我們設計對比 | 3 P1 新增提案（PositionSizer/StrategyHealth/EWMAVol） | 🔴 |
| 2026-04-03 | rust_migration_file_coverage_audit.md | 36 遺漏文件分類 | 文件層面完整，依賴斷裂需修 | ⚠️ |
| 2026-04-24 | 4.24TodoAudit.md | 10 項 claim 驗證 | 5 通過 / 3 部分 / 2 誤導 | 🟡 |
| 2026-04-24 | full_chain_audit_report.md | **34 新發現**（3C / 9H / 14M / 8L） | 12 活躍（C1-C3 + H1-H9） | 🔴 |

---

## 二、遺漏未入當前 TODO 的 FA 活躍項（按等級）

### 🔴 Critical — 必須立即加入（週期 W1-W2）

#### C-1 · Layer 2 自主推理循環無生產觸發（FA-2026-04-24-C1）
- **源自報告**: full_chain_audit_report.md §2.1
- **描述**: `layer2_engine.py:344 run_session()` 存在 750 行 AI agent 迴圈，但生產環境**0 個 scheduler / cron / event trigger**；僅 GUI 手動觸發（layer2_routes.py:210）
- **影響**: 違反原則 11（Agent 最大自主權）/ 15（多 Agent 協作）；系統完全被動於 tick-driven Rust pipeline，無主動宏觀判斷循環
- **驗證**: grep `run_session` in production code = 0；grep `ensure_future.*engine` in production = 0
- **建議 ID**: `INFRA-LAYER2-AUTONOMY-1` · **P0** · **Wave 2 (W19) 加入**
- **修復工時**: 2-3 天（加 Conductor 自主觸發邏輯：市場波動 / 新 intel / 每 N 小時 / 持倉 loss）

#### C-2 · ExecutorAgent `_shadow_mode=True` 硬寫死未配置化（FA-2026-04-24-C2）
- **源自報告**: full_chain_audit_report.md §2.1 + memory.md 2026-04-24
- **描述**: `executor_agent.py:482` 類屬性 `_shadow_mode: bool = True` 硬編碼；`strategy_wiring.py:468 ExecutorConfig()` 無參數傳遞；`ExecutorConfig` dataclass **無 shadow_mode 欄位**
- **實際效果**: 5-Agent 鏈最後一步永遠 log-only；真實下單全走 Rust tick_pipeline 直接路徑，不經 IPC SubmitOrder
- **違反原則**: 原則 3（AI 輸出≠即時命令）/ 11（Agent 自主）/ 15（多 Agent 協作）
- **驗證**: 代碼層確認，無法透過 TOML/env 覆蓋
- **建議 ID**: `AI-EXECUTOR-SHADOW-PROMOTION-1` · **P0** · **Wave 2 (W19) G3-02 一併處理**
- **修復工時**: 1-2 天（改 ExecutorConfig.shadow_mode + IPC override + promotion decision log）

#### C-3 · Decision Lease 在 Rust 真實交易路徑 0 觸發（FA-2026-04-24-C3）
- **源自報告**: full_chain_audit_report.md §2.1
- **描述**: `governance_hub.acquire_lease()` Python 實作完整（governance_hub.py:693）；但 Rust `intent_processor/` grep `Lease` = **0 命中**；唯一生產呼叫點在 Python ExecutorAgent（已因 C-2 永遠 log-only）
- **根本原因**: 真實交易（Rust engine tick_pipeline → intent_processor → order_manager）完全 bypass Decision Lease
- **違反原則**: 原則 3 直接違反（"AI 輸出≠即時命令" 在 Rust 側未實現）
- **驗證**: grep 全目錄 0 命中；架構圖 vs 實裝不符
- **建議 ID**: `GOVERNANCE-LEASE-RUST-INTEGRATION-1` · **P0** · **決策項（Wave 4）**
- **選項 A**: Decision Lease 是 Python shadow-path-only 工具 → 更新 CLAUDE.md §五 架構圖（0.5d）
- **選項 B**: 在 Rust intent_processor 加 Lease IPC 查詢 gate → 3-5d 大工程
- **建議決策**: A（簡潔）+ 文檔澄清

---

### 🟠 High — 重要缺口（應在 Wave 2-3 補完）

#### H-1 · PerceptionPlane validate_for_decision 生產 0 調用（FA-2026-04-24-H1）
- **源自**: full_chain_audit_report.md §2.2 / memory.md FA-7
- **描述**: `perception_data_plane.py:347 register_data()` 有 2 處調用（scout_routes.py:387,489）；但 `validate_for_decision(data_id)` **僅在 tests（3 個 test 檔）**，production 0
- **影響**: 原則 10（認知誠實）的驗證環節缺失；資料 register 但無人驗證「這筆資料能用嗎」
- **建議 ID**: `PERCEPTION-VALIDATION-WIRING-1` · **P1** · **Wave 2 (W19) G3 並行**
- **修復**: 在 AnalystAgent / StrategistAgent 決策前加 `validate_for_decision()` gate（1d）

#### H-2 · H0_GATE Python 實例 0 消費（FA-2026-04-24-H2）
- **源自**: full_chain_audit_report.md §2.2
- **描述**: `paper_trading_wiring.py:290 H0_GATE = H0Gate()` 創建 + health worker 啟動；但 grep `H0_GATE.` **0 命中**；grep `h0_gate.check()` **0 命中**
- **根本原因**: Rust 側完全無 H0Gate 概念；Python 採樣 5s 但無消費者
- **建議 ID**: `INFRA-H0GATE-INTEGRATION-OR-SUNSET-1` · **P1** · **Wave 1 G1 或 W2**
- **修復選項**: (a) 刪 H0_GATE + H0HealthWorker（DEAD-PY-3），或 (b) 經 IPC 寫入 Rust engine 供 intent_processor 使用（1-2d）

#### H-3 · `openclaw_core` 9 個模組 engine 0 引用（FA-2026-04-24-H3）
- **源自**: full_chain_audit_report.md §2.2 / memory.md full_chain_audit
- **描述**: Rust openclaw_core 中 9/17 模組（attention / attribution / backtest / cognitive / dream / message_bus / opportunity / order_match / portfolio）在 engine 0 引用；共 ~4468 行 Rust 死代碼
- **影響**: 代碼質量差、維護成本、技術債
- **建議 ID**: `RUST-OPENCLAW-CORE-DEAD-CODE-CLEANUP-1` · **P2** · **Wave 3（架構整理）**
- **修復**: (a) 接線 Rust 版本（大工程），或 (b) 標 `#[allow(dead_code)]` 或 (c) 整塊刪除（需決策）

#### H-4 · 6 張 learning schema 表 0 production INSERT（FA-2026-04-24-H4）
- **源自**: full_chain_audit_report.md §2.2 + memory.md 完整清單
- **表單**:
  - `learning.rl_transitions` — 0 INSERT
  - `learning.promotion_pipeline` — 0 INSERT
  - `learning.symbol_clusters` — 0 INSERT
  - `learning.cpcv_results` — 僅 cpcv_validator.py（**無 scheduler**）
  - `learning.ml_parameter_suggestions` — 僅 optuna_optimizer.py（**無 scheduler**）
  - `learning.bayesian_posteriors` — 僅 thompson_sampling.py（**無 scheduler**）
- **影響**: P1-7 LEARNING-PIPELINE-DORMANT-1 只覆蓋 edge 估計；原則 12（持續進化）未達
- **建議 ID**: `LEARNING-ML-TRAINING-SCHEDULER-INTEGRATION-1` · **P1** · **Wave 2 (W19) G4 之後**
- **修復**: 為 5 個 ML 訓練腳本補 scheduler/cron 接線（2-3d）

#### H-5 · ML 訓練腳本 silent-unscheduled（FA-2026-04-24-H5）
- **源自**: full_chain_audit_report.md §2.2
- **腳本**: thompson_sampling / optuna_optimizer / cpcv_validator / dl3_foundation / weekly_report_generator
- **問題**: 無 cron / 無 scheduler 呼叫；只有 test 級覆蓋
- **建議 ID**: `INFRA-ML-CRON-WIRING-1` · **P1** · **Wave 1 G1 之後**
- **修復工時**: 1-2d（補 helper_scripts/cron_*.sh wrapper）

#### H-6 · `learning.exit_features.est_net_bps` 100% NULL write-side gap（FA-2026-04-24-H6）
- **源自**: TODO.md §P0 完成項 + full_chain_audit_report.md §2.2
- **描述**: EDGE-DIAG-1 21 次 phys_lock fires 已接線；但 exit_features 表 est_net_bps 欄位全 NULL
- **影響**: Gate 1 決策品質；下游 ML 訓練 feature gap
- **建議 ID**: `EDGE-DIAG-EST-NET-BPS-WRITER-1` · **P0** · **Wave 3**
- **修復工時**: 1-2d（另案 RCA）

#### H-7 · `strategy_auto_deployer` IPC 部署路徑斷裂疑問（FA-2026-04-24-H7）
- **源自**: full_chain_audit_report.md §2.2
- **描述**: `strategy_wiring.py:585 DEAD-PY-2：PipelineBridge removed`；AUTO_DEPLOYER 仍創建但無 bridge → 部署命令走 IPC？
- **建議 ID**: `STRATEGY-DEPLOYER-VERIFY-E2E-1` · **P2** · **Wave 2 驗證**
- **修復**: 端到端驗證：operator 手動觸發 ScoutAgent intel → 驗證 Rust engine 是否接受新策略 IPC（0.5d 驗證 + 可能 1d 修復）

#### H-8 · `experiment_ledger_snapshot.json` 結構異常（FA-2026-04-24-H8）
- **源自**: TODO.md §P1-7 + full_chain_audit_report.md §2.2
- **描述**: 承襲 P1-7；AnalystAgent 的 hypothesis 追蹤依賴此 snapshot 結構
- **建議 ID**: `EXPERIMENT-LEDGER-STRUCTURE-FIX-1` · **P2** · **Wave 2 P1-7 相關**
- **修復工時**: 1d（另案修復）

#### H-9 · H1 / H4 ThoughtGate 未 Regime-aware（FA-2026-04-24-H9）
- **源自**: 2026-03-31 FA-6 + full_chain_audit_report.md §2.2
- **描述**: `strategist_agent.py:292-389` H1 gate 有 budget/complexity/cooldown 三規則；但未接入 `market_regime.py` 的 Regime 分類
- **影響**: 無法根據市場狀態（trending/ranging/volatile）調整 gate 閾值
- **建議 ID**: `H1-THOUGHTGATE-REGIME-AWARE-1` · **P1** · **Wave 2 (W19) G3 並行**
- **修復**: 在 H1 gate 加 regime 分類查詢 + per-regime 閾值（1-2d）

---

### 🟡 Mid — 功能完整性 Gap（需在 Wave 1-2 補）

#### M-1 · PostOnly 配置反向（FA-13 + 4.24TodoAudit 驗證）
- **源自**: memory.md FA-13 + 4.24TodoAudit 項 7（❌ MISMATCH）
- **描述**: TODO 聲稱 `demo=true, live=false`；實際：
  - `risk_config_demo.toml:40 post_only_limit = false` ❌
  - `risk_config_live.toml:42 post_only_limit = true` ❌
- **影響**: demo 環境無 PostOnly 費用控制；live 環境反向啟動（違反保守原則）
- **建議 ID**: `EDGE-P2-3-POSTONLY-VERIFICATION-1` · **P0** · **Wave 1 (W17/18) G1-05**
- **修復**: operator 確認設計意圖並修正 TOML（0.5d）+ CLAUDE.md 敘述同步

#### M-2 · edge_estimates.json 嚴重不足（FA-14 + 4.24TodoAudit 驗證）
- **源自**: memory.md FA-14 + 4.24TodoAudit 項 9（❌ MISMATCH）
- **描述**: 實測 `_meta.n_cells=1`（grid_trading::ORDIUSDT）vs CLAUDE.md 宣稱 135-162 cells；mtime 2026-04-20 已 4 天停滯
- **根本原因**: `edge_estimator_scheduler.py` daemon 運行或 labels 累積速度遠不及預期
- **影響**: cost_gate / DL / JS 機械無充分邊際數據；1 cell 無法支撐 5 策略決策
- **建議 ID**: `EDGE-ESTIMATOR-SCHEDULER-DIAGNOSIS-1` · **P0** · **Wave 1 (W17/18) G1-01**
- **修復工時**: 2h 診斷 + 可能 1d 修復（scheduler 恢復或 labels 加速）

#### M-3 · StrategistAgent/ExecutorAgent 檔案位置異常（FA-15 + 4.24TodoAudit）
- **源自**: memory.md FA-15 + 4.24TodoAudit 項 8（⚠️ PARTIAL）
- **描述**: CLAUDE.md 敘述位置 `program_code/control_api_v1/app/`；實際 `program_code/exchange_connectors/bybit_connector/control_api_v1/app/`
- **影響**: 無法驗證 StrategistAgent.shadow=False、ExecutorAgent._shadow_mode=True 預設值
- **建議 ID**: `CLAUDE.MD-AGENT-PATH-SYNC-1` · **P1** · **Wave 1 文檔**
- **修復**: 補查新位置、驗證預設值、更新 CLAUDE.md 敘述（0.5d）

#### M-4 · Track P v2 T4 wiring 無法定位（FA-16 + 4.24TodoAudit）
- **源自**: memory.md FA-16 + 4.24TodoAudit 項 3（⚠️ PARTIAL）
- **描述**: 搜 `physical_micro_profit_lock_v2` 無定位結果；推測實現位置在 `exit_features/` 或 `tick_pipeline/` 層但檔名不符
- **建議 ID**: `EDGE-DIAG-TRACK-P-LOCATE-1` · **P1** · **Wave 1 驗證**
- **修復**: `grep -r "physical_micro_profit\|phys_lock\|Priority 6" rust/openclaw_engine/src/` 補查（0.5d）

#### M-5 · ATR 倍數配置（Batch 9A 規格，未入 Wave 1）
- **源自**: adaptive_params_functional_spec.md §A（Batch 9A）
- **描述**: `ATRMultipliers` dataclass 應包含 `k_sl / k_tp / k_act / k_trail`；並透過 `operator_risk_config.json` 配置 bounds
- **建議 ID**: `ADAPTIVE-ATR-MULTIPLIERS-IMPLEMENT-1` · **P1** · **Wave 1 G1 之後**
- **修復工時**: 1-2d（dataclass 定義 + TOML 綁定 + 風控邏輯接線）

#### M-6 · 成本感知入場門檻（Batch 9A 規格，未入 Wave 1）
- **源自**: adaptive_params_functional_spec.md §B（Batch 9A）
- **描述**: 新增 `compute_round_trip_cost_pct(symbol, volume_24h, category)` + 在 `pipeline_bridge._process_single_intent()` 中檢查 `ATR < min_move_pct` → reject
- **建議 ID**: `ADAPTIVE-COST-AWARE-ENTRY-GATE-1` · **P1** · **Wave 1 G1 之後**
- **修復工時**: 1-2d

#### M-7 · Regime-aware 參數映射表（Batch 9A 規格）
- **源自**: adaptive_params_functional_spec.md §C（Batch 9A）
- **描述**: `REGIME_ATR_MULTIPLIERS` 代碼常量，per-regime 不同倍數值
- **建議 ID**: `ADAPTIVE-REGIME-ATR-MAPPING-1` · **P1** · **Wave 1 G1 完成後**
- **修復工時**: 1d

#### M-8 · 追蹤止損 ATR 公式化（Batch 9A 規格）
- **源自**: adaptive_params_functional_spec.md §A3（Batch 9A）
- **描述**: 修改 `_check_stops()` 追蹤止損部分，啟動 = `max(c_round_pct * 2.5, k_act * atr_pct)`；距離 = `max(c_round_pct, min(k_trail * atr_pct, hard_sl * 0.8))`
- **建議 ID**: `ADAPTIVE-TRAILING-STOP-FORMULA-1` · **P1** · **Wave 1 G1 完成後**
- **修復工時**: 1d

#### M-9 · 背景 — FundingArb 成本模型（Batch 9A-E）
- **源自**: improvement_report_gap_comparison.md §2.4（FundingRateArb V2）
- **描述**: 加 funding 歷史 + basis risk 量化；與報告 Paired Execution 衍生新需求
- **建議 ID**: `STRATEGY-FUNDINGARB-COST-MODEL-1` · **P1** · **Wave 2-3 EDGE-P2-2 Phase B**
- **修復工時**: 2-3d

#### M-10 · PositionSizer 四層（改善報告 §1.1 → P1 新增）
- **源自**: improvement_report_gap_comparison.md §2.7（PositionSizer 四層）
- **描述**: Kelly Fraction（根據樣本量折扣）+ Volatility Adjusted + Risk Parity + P1 硬上限
- **建議 ID**: `STRATEGY-POSITIONSIZER-MULTI-LAYER-1` · **P1** · **Wave 2 (W19)**
- **修復工時**: 1d（純只讀工具，無副作用）

#### M-11 · StrategyHealthMonitor + CUSUM（改善報告 §1.2 → P1 新增）
- **源自**: improvement_report_gap_comparison.md §2.8（StrategyHealthMonitor）
- **描述**: 滾動 Sharpe/WR + CUSUM 衰減檢測 + 15 連虧硬性暫停
- **建議 ID**: `STRATEGY-HEALTH-CUSUM-MONITOR-1` · **P1** · **Wave 2 (W19)**
- **修復工時**: 1d

#### M-12 · EWMAVolEstimator + HurstExponent（改善報告 §1.3~1.4 → P1 新增）
- **源自**: improvement_report_gap_comparison.md §2.9（EWMAVolEstimator + Hurst）
- **描述**: EWMA 波動率估計器（vs ATR）+ Hurst Exponent（趨勢/均值回歸/隨機區分）
- **建議 ID**: `INDICATOR-EWMA-HURST-ADD-1` · **P1** · **Wave 2 (W19)**
- **修復工時**: 1d（兩者都只讀工具）

#### M-13 · ContextDistiller（改善報告 §2.8 → P1 新增）
- **源自**: improvement_report_gap_comparison.md §2.4（ContextDistiller）
- **描述**: 壓縮系統狀態為 ~450 tokens 摘要，API 調用時只發摘要+問題減少 token 浪費
- **建議 ID**: `AI-CONTEXT-DISTILLER-IMPL-1` · **P1** · **Wave 2 (W19) G4 並行**
- **修復工時**: 0.5-1d（純只讀壓縮）

#### M-14 · APIBudgetManager 擴展（改善報告 §4.4 → P1 新增）
- **源自**: improvement_report_gap_comparison.md §2.5（APIBudgetManager）
- **描述**: 月度預算管理 + 持久化 + 冷卻期 + 月重置（擴展現有 Layer2CostTracker）
- **建議 ID**: `AI-BUDGET-MANAGER-PERSISTENCE-1` · **P1** · **Wave 2 (W19) G4**
- **修復工時**: 0.5d（已有骨架）

---

### ⚪ Low（可延後，P3 等級）

#### L-1 · TruthSourceRegistry 無持久化（FA-6，已部分修2026-04-01 P0-FA-1）
- 已登記但 save_snapshot() 未在任何地方調用
- **建議 ID**: `LEARNING-TRUTH-REGISTRY-PERSIST-1` · **P2** · **Wave 3 後半**

#### L-2 · MAX_SYMBOLS_TO_TRADE 配置不一致（FA-2026-04-01 殘留）
- MarketScanner=5 vs StrategyAutoDeployer=25
- **建議 ID**: `CONFIG-MAX-SYMBOLS-UNIFY-1` · **P3**

#### L-3 · XP-1 路徑不硬編碼（完全保留，部分瘦身，修改 Python）
- 跨平台相容性，已規範
- **建議 ID**: `CROSS-PLATFORM-PATH-HARDCODE-FIX-1` · **P3**

#### L-4 · V999 migration 版本號衝突（M5 的 downstream）
- 應改名為 V024 或 rollback delete
- **建議 ID**: `MIGRATION-V999-RENAME-1` · **P3**

#### L-5 · 多個 TODO / FIXME 標記（60 Rust + 127 Python）
- 定期 triage
- **建議 ID**: `CODE-TODO-TRIAGE-1` · **P3 持續**

#### L-6 · `_scout_worker` singleton 未登記 CLAUDE.md §九
- **建議 ID**: `CLAUDE.MD-SINGLETON-AUDIT-UPDATE-1` · **P3**

#### L-7 · `correlated_exposure_max_pct` TOML vs runtime 漂移（M1）
- TOML=60.0 但 runtime=65.0
- **建議 ID**: `CONFIG-CORRELATED-EXPOSURE-SYNC-1` · **P3**

---

## 三、FA 完整 TODO 提案（按波次）

### Wave 1（W17/18）— 基礎設施解凍 + 驗證

**G1 項目（必須）**:
1. **G1-01-FA**: `EDGE-ESTIMATOR-SCHEDULER-DIAGNOSIS-1` [P0 · M-2]
2. **G1-02-FA**: `EDGE-P2-3-POSTONLY-VERIFICATION-1` [P0 · M-1]
3. **G1-05-FA**: `ADAPTIVE-ATR-MULTIPLIERS-IMPLEMENT-1` [P1 · M-5]
4. **G1-05-FA2**: `ADAPTIVE-COST-AWARE-ENTRY-GATE-1` [P1 · M-6]
5. **G1-05-FA3**: `ADAPTIVE-REGIME-ATR-MAPPING-1` [P1 · M-7]
6. **G1-05-FA4**: `ADAPTIVE-TRAILING-STOP-FORMULA-1` [P1 · M-8]
7. **G1-01-FA2**: `INFRA-ML-CRON-WIRING-1` [P1 · H-5]

**G6 項目（合規）**:
- `CLAUDE.MD-AGENT-PATH-SYNC-1` [P1 · M-3]
- `EDGE-DIAG-TRACK-P-LOCATE-1` [P1 · M-4 驗證]

### Wave 2（W19）— AI 接線 + 架構合規

**G3 項目（AI 接線）**:
1. `AI-EXECUTOR-SHADOW-PROMOTION-1` [P0 · C-2] — 與既有 G3-02 一併處理
2. `GOVERNANCE-LEASE-RUST-INTEGRATION-1` [P0 · C-3] — 決策項，澄清架構意圖
3. `INFRA-LAYER2-AUTONOMY-1` [P0 · C-1]
4. `H1-THOUGHTGATE-REGIME-AWARE-1` [P1 · H-9]
5. `PERCEPTION-VALIDATION-WIRING-1` [P1 · H-1]

**G4 項目（ML 管線）**:
1. `LEARNING-ML-TRAINING-SCHEDULER-INTEGRATION-1` [P1 · H-4]
2. `AI-CONTEXT-DISTILLER-IMPL-1` [P1 · M-13]
3. `AI-BUDGET-MANAGER-PERSISTENCE-1` [P1 · M-14]

**G5 項目（架構）**:
- （existing）

**G2 項目（策略層）**:
- `STRATEGY-DEPLOYER-VERIFY-E2E-1` [P2 · H-7 驗證] 
- `STRATEGY-POSITIONSIZER-MULTI-LAYER-1` [P1 · M-10]
- `STRATEGY-HEALTH-CUSUM-MONITOR-1` [P1 · M-11]
- `INDICATOR-EWMA-HURST-ADD-1` [P1 · M-12]

**其他**:
- `INFRA-H0GATE-INTEGRATION-OR-SUNSET-1` [P1 · H-2]

### Wave 3（W20-W23）— Edge 穩定 + ML canary

1. `EDGE-DIAG-EST-NET-BPS-WRITER-1` [P0 · H-6]
2. `EXPERIMENT-LEDGER-STRUCTURE-FIX-1` [P2 · H-8]
3. `RUST-OPENCLAW-CORE-DEAD-CODE-CLEANUP-1` [P2 · H-3]
4. `STRATEGY-FUNDINGARB-COST-MODEL-1` [P1 · M-9]
5. `LEARNING-TRUTH-REGISTRY-PERSIST-1` [P2 · L-1]

### Wave 4（W23-W24）— Live Gate 簽準

- 決策 `GOVERNANCE-LEASE-RUST-INTEGRATION-1` 方案（C-3）

### P3（中期，可延後）

- `CONFIG-MAX-SYMBOLS-UNIFY-1`
- `CROSS-PLATFORM-PATH-HARDCODE-FIX-1`
- `MIGRATION-V999-RENAME-1`
- `CODE-TODO-TRIAGE-1`（持續）
- `CLAUDE.MD-SINGLETON-AUDIT-UPDATE-1`
- `CONFIG-CORRELATED-EXPOSURE-SYNC-1`

---

## 四、功能 Mismatch 專項清單

### 代碼聲稱 ≠ 實作對照表

| Claim 來源 | 聲稱 | 實際代碼 | Gap | 檔案:行 |
|---------|------|-------|-----|--------|
| CLAUDE.md §三 | `edge_estimates.json` 135-162 cells | 1 cell (`_meta.n_cells=1`) | 🔴 高 | settings/edge_estimates.json |
| CLAUDE.md §三 | `demo/paper=true, live=false` PostOnly | demo=false, live=true（反向） | 🔴 高 | settings/risk_config_demo.toml:40 / risk_config_live.toml:42 |
| CLAUDE.md §三 | ExecutorAgent shadow 可配置切換 | `_shadow_mode=True` 硬編碼 + `ExecutorConfig()` 無欄位 | 🔴 高 | executor_agent.py:482 / strategy_wiring.py:468 |
| CLAUDE.md §三 | Layer 2 自主推理循環 | 0 scheduler/cron 觸發，僅 GUI 手動 | 🔴 高 | layer2_routes.py:210 |
| CLAUDE.md §三 | Decision Lease 在交易路徑 | Rust intent_processor grep `Lease`=0 | 🔴 高 | intent_processor/ · governance_hub.py:693 |
| CLAUDE.md §五 | 架構圖 [I Decision Lease] | 實際 Python shadow-path-only | ⚠️ 中 | CLAUDE.md §五 vs executor_agent.py:342 |
| CLAUDE.md §三 | H0_GATE 本地判斷內核 | Python 採樣但 0 消費；Rust 無此概念 | 🟡 中 | paper_trading_wiring.py:290 vs engine 0 引用 |
| CLAUDE.md §三 | 5-Agent MessageBus 全路徑 | Guardian 發 RISK_VERDICT 不發 APPROVED_INTENT 給 Executor | 🟡 中 | guardian_agent.py:289-298 vs executor_agent.py:201 |
| TODO.md §P0-13/14 | edge 充分性 | 1 cell 遠不足支撐 5 策略決策 | 🟡 中 | settings/edge_estimates.json / P1-7 |
| 4.24TodoAudit | StrategistAgent / ExecutorAgent 檔案位置 | 實際位置多層嵌套 `exchange_connectors/.../` | ⚠️ 低 | 預期 program_code/control_api_v1/ vs 實際位置 |

---

## 五、給 PA 的核實指引（優先順序）

### Tier 1（必須優先驗證，涉及 Live Gate 通過條件）

1. **PostOnly 配置反向** (M-1)
   - 驗證：讀 `settings/risk_config_demo.toml:40` + `risk_config_live.toml:42` 實際值
   - operator 確認設計意圖
   - 待機修正並重部署

2. **edge_estimates 狀態** (M-2)
   - 驗證：`settings/edge_estimates.json` 當前 n_cells 值
   - 確認 `edge_estimator_scheduler.py` daemon 是否持續運行（`ps aux | grep edge_estimator`）
   - 若停滯，root cause analysis + scheduler 修復優先

3. **ExecutorAgent shadow_mode** (C-2)
   - 驗證：`executor_agent.py:482` 是否仍硬編碼 True
   - 驗證：`strategy_wiring.py:468 ExecutorConfig()` 是否仍無參數
   - 確認 `ExecutorConfig` dataclass 是否有 shadow_mode 欄位
   - 決定 C-3（Decision Lease）架構意圖（Python shadow-path vs Rust integration）

4. **Decision Lease Rust 側** (C-3)
   - 驗證：`rust/openclaw_engine/src/intent_processor/` grep `Lease` 結果
   - 決策：(a) 更新文檔 vs (b) 實現 Rust 側 Lease IPC gate
   - 若選 (a)，更新 CLAUDE.md §五 架構圖

### Tier 2（Wave 1-2 開工前必清）

5. **Layer 2 自主循環** (C-1)
   - 驗證：是否有任何 scheduler/cron/event 觸發 `layer2_engine.run_session()`
   - 若無，決定：是否加 Conductor 自主觸發邏輯

6. **H0_GATE 消費路徑** (H-2)
   - 驗證：grep `H0_GATE.` in `control_api_v1` 完整結果
   - 決定：刪除（DEAD-PY-3）vs 經 IPC 寫 Rust engine

7. **ML 訓練 scheduler 接線** (H-4 / H-5)
   - 驗證：5 個 ML 腳本是否有對應 `helper_scripts/cron_*.sh`
   - 確認 `learning.*` 表的生產 INSERT 路徑

### Tier 3（Wave 2-3 執行期監控）

8. **Batch 9A 規格實現** (M-5 ~ M-8)
   - 驗證：ATRMultipliers dataclass 是否已在 risk_manager.py
   - 驗證：成本門檻 gate 是否已接線 pipeline_bridge
   - 驗證：Regime mapping 是否已編碼

9. **改善報告 P1 新增項** (M-10 ~ M-14)
   - 驗證：PositionSizer / StrategyHealth / EWMAVol / ContextDistiller / APIBudgetManager 實現進度

---

## 六、總結

### 遺漏未入當前 TODO 的 FA 活躍項數

| 等級 | Critical | High | Mid | Low | 合計 |
|------|----------|------|-----|-----|------|
| 數量 | 3 | 9 | 14 | 8 | **34** |
| 已入 TODO | 0 | 1（P1-7） | 4（P0-13/14/15 + EDGE-DIAG） | 0 | **5** |
| **待補** | **3** | **8** | **10** | **8** | **29** |

### 完整 TODO 提案條目

- **Wave 1 新增**: 7 項 FA 活躍項 + 既有 G1-01~05
- **Wave 2 新增**: 13 項 FA 活躍項（C2/C1 + H1/H2/H9 + M-10~14 等）
- **Wave 3 新增**: 5 項 FA 活躍項（H6/H8/H3 + L-1 + M-9）
- **Wave 4 決策**: C-3 Lease 定位確認
- **P3 中期**: 6 項 Low 級項目

### 關鍵 Root Cause 排序

1. **edge_estimator_scheduler 4 天停滯** → 加速 labels 累積 → Edge 穩定 → Phase 5 放權 → Live
2. **PostOnly 配置反向** → 修正 TOML + 驗證 gate 行為 → 策略費用控制生效
3. **ExecutorAgent hardcoded shadow** → 改 config + IPC override → 5-Agent 鏈完整 → AI 治理完整
4. **Decision Lease Rust 側斷裂** → 決策架構意圖（shadow-path vs engine integration）

---

**報告日期**: 2026-04-24 CEST  
**簽署**: FA (Functional Auditor)  
**下一步**: PA 整合本報告至 TODO.md；Wave 1 開工前清算 Tier 1 驗證
