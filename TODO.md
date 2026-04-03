# OpenClaw TODO — 工作計劃清單
# 最後更新：2026-04-03（Phase R-01 完成 · Rust 65 tests · Python 3703 passed · 關鍵路徑 R-02）
# 注意：compact 後從此文件恢復工作狀態
# ★ 排查參考：docs/KNOWN_ISSUES.md（已識別但未驗證的風險，遇到異常時先查）

---

## 強制工作流程

```
任何修復/功能 → E1/E1a 並行執行 → E2 代碼審查（必須）→ E4 全量回歸（必須）→ PM 確認 → commit
緊急通道（P0）：跳過 FA/A3/R4，但 E2+E4 絕對不可跳過
最大並行：5 個 E1 Agent 同時修不同文件
16 角色定義詳見 CLAUDE.md §八
```

---

## 測試基準線

```
3703 passed / 24 failed / 17 errors（post Phase 3 · test_create_basic 為 pre-existing）
命令：python3 -m pytest --ignore=database_files -q --tb=no
```

---

## 已完成項歸檔

```
Wave 0-7 / Phase 1-3 / Audit Batch 1-7 / main_legacy 重構：
  → docs/worklogs/control_api_gui/2026-04-01--completed_todo_archive.md

Batch 9A + XP-1~4 + Wave 8A-8D：
  → docs/worklogs/2026-04-03--completed_todo_archive_batch9a_wave8_xp.md

SPEC 審查記錄：
  → 認知自適應 V1.1+R1：docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md
  → Rust 遷移 V3-FINAL：docs/references/2026-04-03--rust_migration_v3_final.md
```

---

## 全局路線圖概覽

```
★ 當前焦點 → Phase 2-L1 凍結 → Phase 3（讀下方第一個 [ ] 開始）

Phase 0（本週 · 5d）  業務 52%→72%    學習閉環 + 管線連通 + 策略 Edge
Phase 1（Week 2-3 · 9d）業務→82%     感知工具箱 + 認知三模組 + ★R-00 並行
Phase 2（Week 3-5 · 10d）業務→93%    策略 V2 + Agent 整合 + ★L1 凍結
Phase 3（Week 5-7 · 8d） 業務→100%   Claude API + 放權 + ★L2 凍結
Phase R（Week 8-21 · 70d）性能+容錯   Rust 遷移 14 週 → 見 docs/rust_migration/
Phase 4（條件性）                      條件觸發項
Live Gate                             Paper 21 天 + Live 準備

Alpha 基準：Phase 0 Day 1 並行跑 Paper 2 週 · Day 10 決策點
  PnL > 0 → 繼續 · PnL ≈ 0 → 繼續但提升策略優先級 · PnL < -3% → 暫緩轉策略研究
```

---

## ██ Phase 0-A — 學習閉環 + 管線連通（Day 1-3，~14h，5 E1 並行）

> 業務完成度 52%→~72%。全部可並行。

### [x] 0A-1：學習反饋閉環（原 U-01 · FA P0-GAP-1）
- **檔案**：`app/strategist_agent.py` + `app/pipeline_bridge.py`
- **修復**：get_strategy_weight() + PipelineBridge 門控前應用學習權重
- **工時**：4h · **E1**：E1-Alpha

### [x] 0A-2：進化參數自動重部署（原 U-02 · FA P0-GAP-2）
- **檔案**：`phase2_strategy_routes.py` + `evolution_routes.py`
- **修復**：evolution_routes.set_auto_deployer(AUTO_DEPLOYER) 啟動時注入
- **工時**：4h · **E1**：E1-Beta

### [x] 0A-3：H0 Gate shadow 觀察（原 U-06 · FA P1-GAP-3）
- **修復**：shadow_mode 旗標 + _check_shadow() + shadow stats/log
- **工時**：1h · **E1**：E1-Gamma

### [x] 0A-4：Scanner→Deployer 自動接通（原 U-07 · FA P1-GAP-5）
- **驗證**：已於 phase2_strategy_routes.py:696 完整接通，無需修改
- **工時**：2h · **E1**：E1-Delta

### [x] 0A-5：Backtest 生產環境啟用（原 U-08 · FA P1-GAP-6）
- **修復**：AutoDeployer.set_backtest_engine() + _validate_strategy_backtest() 部署前回測
- **工時**：2h · **E1**：E1-Epsilon

### [x] 0A-6：L2 觸發門檻降低 50→20（原 U-15 · FA P2-GAP-7）
- **修復**：AnalystConfig.l2_min_observations default 50→20
- **工時**：1h · **E1**：E1-Gamma

---

## ██ Phase 0-B — 策略 Edge 驗證（Day 3-5，~15h，3 E1 並行）

### [x] 0B-1：FundingRateArb 完整成本模型精算（原 U-10 · QC S3）
- **修復**：滑點建模 + 基差風險追蹤 + 多周期攤薄 + 持倉成本追蹤 + get_cost_summary()
- **工時**：6h · **E1**：E1-Alpha · **依賴**：0A-5

### [x] 0B-2：交易所條件單 SL/TP（原 U-11 · FA P1-GAP-4）
- **修復**：SL 5% + TP 8%（PipelineBridge + Executor callback）；原則 9 雙重防線完整
- **工時**：6h · **E1**：E1-Beta · **E3 安全審查**：fail-open 模式確認

### [x] 0B-3：Kelly fraction + GUI + Agent 自動資本分配（原 U-14 · QC S4）
- **新建**：position_sizer.py（Kelly 四層計算）+ tab-ai.html Kelly 卡片 + API 端點
- **整合**：AutoDeployer.get_kelly_recommendations() + 部署前回測驗證
- **工時**：3h · **E1**：E1-Gamma

---

## ██ Phase 1 — Agent 感知工具箱 + 認知三模組（Week 2-3，~9 天壁鐘）

> 前置：Phase 0 完成。
> ★ Rust R-00 提前並行從本 Phase Day 1 開始 → 見 `docs/rust_migration/00--preparation_parallel.md`

### 並行組 A（無依賴，同時開工）

### [x] 1-1：PositionSizer — Kelly 四層倉位計算（報告 §5.1）
- **已在 0B-3 完成**：position_sizer.py（Kelly 四層 + Vol-adjusted + Risk Parity + P1 上限）
- **工時**：1d（含在 0B-3）

### [x] 1-2：StrategyHealthMonitor — CUSUM 策略衰減檢測（報告 §5.2）
- **新建**：strategy_health_monitor.py（rolling Sharpe + CUSUM + 15 連虧硬性兜底）

### [x] 1-3：EWMAVolEstimator — 波動率估計（報告 §5.3）
- **新建**：ewma_vol_estimator.py（Lambda 衰減 + 在線方差 + vol regime 分類）

### [x] 1-4：Hurst Exponent — R/S 分析（報告 §5.4）
- **新建**：hurst_exponent.py（R/S 重標極差 + log-log 線性回歸）

### 並行組 B（1-3/1-4 接口就緒後）

### [x] 1-5：Indicator Engine 擴展 — 6 新指標（報告 §6.6）
- **新建**：indicators/extended.py（KAMA, ADX, HurstIndicator, EWMAVolIndicator, VolumeRatio, DonchianChannel）
- **附帶**：SMA 改用 math.fsum() [V3-QC-2]

### [x] 1-6：CognitiveModulator — L0 決策門檻調製（認知 SPEC §2）
- **新建**：cognitive_modulator.py（[Q1] max 單因子 + [Q6] EMA α=0.3 + [R1-5] 連虧忽略負向）
- **降級**：regret_data={}, dream_data={} 傳空 dict

### [x] 1-7：OpportunityTracker — 虛擬 PnL 追蹤（認知 SPEC §3）
- **新建**：opportunity_tracker.py（[Q2] 扣 2x fee + [Q3] 歸一化 + [R1-8] ≥5 樣本）

### [x] 1-8：DreamEngine — 閒置蒙特卡洛模擬（認知 SPEC §4）
- **新建**：dream_engine.py（[Q4] ≥30 輪/參數 + [Q5] binomial test + [R1-3] reentrancy guard）
- **暫不接入** CognitiveModulator（Phase 2 啟用）

### 並行組 C

### [x] 1-9：LocalLLMClient 抽象 — Ollama + LM Studio 兼容（報告 §4.5）
- **新建**：local_llm_client.py（ABC + OllamaProvider + LMStudioProvider）

### [x] 1-10：影子決策追蹤 — 四階段退出條件數據（報告 §2）
- **新建**：shadow_decision_tracker.py（四階段假設退出比較）

---

## ██ Phase 2 — 策略 V2 + Agent 整合（Week 3-5，~10 天壁鐘）· ★L1 凍結

> 前置：Phase 1 完成 + Alpha 基準 2 週結果。
> ★ Phase 2 結束 → L1 接口凍結（indicator/signal/h0_gate/strategies）

### [x] 2-1：MA_Crossover V2 — KAMA + ADX>20 + 多時間框架（報告 §6.1）
### [x] 2-2：BB_Reversion V2 — RSI<30 + Regime 感知（報告 §6.2）
### [x] 2-3：BB_Breakout V2 — Volume ratio>1.5 + Donchian（報告 §6.3）
### [x] 2-4：FundingRateArb V2 — Paired Execution + Basis（報告 §6.4）
### [x] 2-5：GridTrading V2 — OU 動態間距 + 成本修正（報告 §6.5）
### [x] 2-6：Regime Detection 升級 — Hurst + EWMA Vol（報告 §3）
### [x] 2-7：Strategist 雙軌 + CognitiveModulator 閉環（報告 §3.3 + 認知 SPEC §5.1.2）
### [x] 2-8：ContextDistiller — ~520 tokens · **Rust+PyO3**（報告 §4.2 + 認知 SPEC §5.1.1）
### [x] 2-9：Ollama prompt 模板 + cognitive/dream 欄位（認知 SPEC §6.2）
### [x] 2-L1：★ L1 接口凍結簽核 → git tag `l1-interface-freeze`（2026-04-03 Operator 確認）

---

## ██ Phase 3 — Claude API + 四階段放權（Week 5-7，~8 天壁鐘）· ★L2 凍結

### [x] 3-1：Claude API 客戶端 + APIBudgetManager（報告 §4.4）
### [x] 3-2：L1→L1.5→L2 路由邏輯（報告 §4.1）
### [x] 3-3：Claude→TSR 閉環 — knowledge_update + TTL（報告 §4.3）
### [x] 3-4：HedgingEngine — delta 計算 + 對沖建議（報告 §5.5）· **Rust+PyO3**
### [x] 3-5：PnLAttributor + API + GUI（報告 §5.6）· Python 擴展現有 TradeAttributionEngine
### [x] 3-6：OB Imbalance + Orderbook WS（報告）
### [x] 3-7：四階段放權框架 — DelegationFramework 獨立模組 + 自動降級（報告 §2）
### [x] 3-L2：★ L2 接口凍結簽核 → git tag `l2-interface-freeze`（2026-04-03 Operator 確認）

---

## ██ Phase R — Rust 遷移（Week 8-21，14 週主開發）

> **源文件**：`docs/references/2026-04-03--rust_migration_v3_final.md`
> **階段文件**：`docs/rust_migration/`（8 個文件，Agent 接手先讀 README.md）
> **前置**：Phase 0-3 全部完成 + L1+L2 凍結 + Alpha PnL > 0

### [x] R-00：提前並行（Phase 1-3 期間）— Cargo workspace ✅ + PyO3 ✅ + types ✅ + CI ✅ + L1/L2凍結 ✅（告警 bot 延後）
### [x] R-01：IPC + shared_types + WS（W1-2）— workspace 統一 + openclaw_pyo3 crate + 4 engine 模組 + 3 Python 模組 + schema diff CI
### [x] R-02：core 上半——感知 + 認知 + 風控（W3-4）— 10 模組 + 302 Rust tests + Golden Dataset 驗證
### [x] R-03：core 下半——SM + 執行 + 回測（W5-6）— 4 SM + GovernanceCore 級聯 + 9 模組 + 468 Rust tests + 極端組 PASS
### [x] R-04：Engine 完整交易路徑（W7-8）— tick_pipeline + 5 策略 + paper_state + persistence + 517 Rust tests
### [x] R-05：★ Conditional Go 簽核（2026-04-03）— 5/6 PASS + 3 風險待 soak test（見 KNOWN_ISSUES.md）
### [x] R-06：Python IPC 改造（W9-10）— 53 IPC tests PASS，回滾 SLA <100ms，R06-C 延至 R-07
### [~] R-07：灰度驗證 + 穩定觀察（W11-14）— R07-2/3/5/6 ✅，R07-1 影子進程待做，R07-4 7天灰度待啟動

> 每個 R-xx 的詳細子任務見 `docs/rust_migration/0x--*.md`

---

## ██ ★★★ 重點優化待辦（架構債務 · 高優先級）

### [ ] ★ AGT-1：策略參數運行時可調 + Agent 真正「使用」策略模型工具

**問題核心（2026-04-03 發現）：**
Agent（Strategist）與策略模型（MA/BB/Grid 等）目前完全平行、互不干涉：
- 策略靠 SignalEngine → StrategyOrchestrator → strategy.on_signal() 自動運行，Agent 從不調用策略
- 所有 V2 參數（adx_threshold / use_kama / rsi_threshold / regime_aware / ou_dynamic 等）在構造後不可變
- Create API 只傳 qty_per_trade，其他 V2 參數全靠硬編碼默認值
- Agent 的學習只影響推薦置信度權重，不影響任何策略行為

**需要實現的三件事：**
1. **策略 `update_params()` 方法** — 允許運行時修改 V2 參數（線程安全）
2. **`PATCH /api/v1/strategy/{name}/params` 端點** — Operator 或 Agent 可調整現有策略參數
3. **Create API 傳入完整 V2 參數** — Auto-Deployer 和 Strategist 在部署策略時帶參數，而不是全用默認值

**影響範圍：** `strategies/base.py` + 5 個策略文件 + `phase2_strategy_routes.py` + `strategy_auto_deployer.py`
**優先級：** Phase 2 之後、Phase R 之前（L1 接口凍結前必須決定是否納入）
**工作量估算：** ~2d（E1×2 並行）

---

## ██ Phase 4 — 條件性（有前置條件觸發）

### [ ] 4-1：PairsTrading（需 3 月協整驗證）
### [ ] 4-2：Beta Hedging（需 HedgingEngine 穩定 1 月）
### [ ] 4-3：Kalman Filter（KAMA 表現不理想時）
### [ ] 4-4：JSON→PostgreSQL（數據量瓶頸時）
### [ ] 4-5：Mac Studio 遷移 + 大模型（硬件到手）
### [ ] 4-6：L5 meta-learning（原 C3，需 FA 規格 + PA 方案）
### [ ] 4-7：統計適應硬門檻（200+ trades/regime，原 U-12）
### [ ] 4-8：Walk-forward harness（原 U-16）
### [ ] 4-9：Deflated Sharpe Ratio（原 U-17）
### [ ] 4-10：Jump detection — K 線 body > 3σ → 加寬止損（原 U-18）
### [ ] 4-11：CLAUDE.md §3 歷史歸檔（原 D2，minor 20min）

---

## ██ Live Gate — Paper 21 天 + Live 準備

> 前置：Phase 3 完成 + Phase R 完成（或 PyO3 降級穩定）+ Alpha > 0

### [ ] LG-1：Paper Trading 穩定運行 21 天驗證
### [ ] LG-2：H0 Gate blocking 驗證（shadow→blocking 切換）
### [ ] LG-3：provider pricing table 正式綁定
### [ ] LG-4：M 章 Supervised Live Gate
### [ ] LG-5：N 章 Constrained Autonomous Live

---

## ██ 長期整合（非緊急）

### [ ] OC-1：OpenClaw Webhook 告警（1-2d · 零 AI 成本）
### [ ] OC-2：Telegram 通道配置（0.5d）
### [ ] OC-3：多通道分級告警（1d · 依賴 OC-2）
### [ ] OC-4：MCP PostgreSQL 自然語言查詢（1d）

---

## Paper-Demo 差異校準（中長期）

### 中期
- [ ] tab-trading.html 標示 Paper vs Demo 數據來源
- [ ] Paper-Demo 差異率儀表板
- [ ] 對賬引擎 reconcile() GUI 可視化

### 長期
- [ ] Demo 實際滑點 → PostgreSQL → 校準 Paper SLIPPAGE_TIERS
- [ ] 費率校準：Paper 硬編碼 vs Demo 實際
