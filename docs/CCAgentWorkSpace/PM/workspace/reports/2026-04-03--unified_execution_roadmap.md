# 統一執行路線圖 — OpenClaw 中期開發計劃
# Unified Execution Roadmap — OpenClaw Mid-term Development Plan

> 制定人：PM（Project Manager）
> 日期：2026-04-03
> 輸入來源：
>   - Batch 9B-9D 計劃（2026-04-02--adaptive_params_execution_plan.md）
>   - 外部改善報告 V3 Final（2026-04-03--openclaw_improvement_report_v3_final.md）
>   - Operator 決策（2026-04-02，4 項確認）
>   - Batch 9A 已完成（commit d9b102f，3703 tests）
> 測試基準：3,703 passed
> 系統狀態：demo_only · live_execution_allowed=false

---

## 0. Executive Summary

兩套計劃存在顯著重疊。Batch 9B-9D 的 13 項任務中，8 項與報告 Phase 1 直接對應。報告新增的
~20 項任務主要集中在策略升級（Phase 2）和 API/框架（Phase 3），屬於中長期投資。

**合併策略：** Batch 9B-9D 是報告 Phase 1 的子集，直接作為 Phase 0 執行。報告的 Phase 1
非重疊項插入為 Phase 1。Phase 2/3 保持報告原結構但按 5 天切分。

**核心風險前置：** 報告的 C.1「策略 Alpha 基準測試」（2 週 Paper Trading）從 Phase 0 第一天
開始並行跑，不佔開發時間。這是「是否值得繼續」的第一個決策點。

**總體規模：** 4 個 Phase + 1 個條件性 Phase = ~36 工作日 = ~7 週壁鐘
（含 E2+E4 驗收、Paper 觀察、緩衝）

---

## 1. 重疊分析

### 1.1 Batch 9B-9D vs 報告 Phase 1 對照

| Batch 9 項目 | 報告 Phase 1 項目 | 關係 |
|-------------|------------------|------|
| U-01 學習反饋閉環 | 1.6 學習反饋迴路修復 | **完全重疊** |
| U-02 進化參數重部署 | 1.7 Evolution→Deploy | **完全重疊** |
| U-06 H0 Gate shadow | — | **Batch 獨有**（報告未涉及 H0 shadow 觀察） |
| U-07 Scanner→Deployer | — | **Batch 獨有**（報告假設已接通） |
| U-08 Backtest 啟用 | — | **Batch 獨有**（報告假設已可用） |
| U-15 L2 門檻降低 | — | **Batch 獨有**（報告未涉及） |
| U-10 FundingRateArb 精算 | 2.4 FundingRateArb V2 | **部分重疊**（Batch 做成本模型，報告做完整策略升級） |
| U-11 交易所條件單 | — | **Batch 獨有**（報告假設已有） |
| U-14 Kelly fraction GUI | — | **部分重疊**（報告 5.1 PositionSizer 含 Kelly） |
| — | 1.1 PositionSizer | **報告獨有** |
| — | 1.2 StrategyHealthMonitor | **報告獨有** |
| — | 1.3 EWMAVolEstimator | **報告獨有** |
| — | 1.4 Hurst 計算 | **報告獨有** |
| — | 1.5 Indicator Engine 擴展 | **報告獨有** |
| — | 1.8 LocalLLMClient 抽象 | **報告獨有** |
| — | 1.9 影子決策追踪 | **報告獨有** |

### 1.2 合併結論

- **Phase 0**：Batch 9B + 9C + 9D（13 項，已有完整 PA 技術方案，直接執行）
- **Phase 1**：報告 Phase 1 非重疊項（1.1-1.5, 1.8, 1.9 = 7 項）
- **Phase 2**：報告 Phase 2（策略升級 + Agent 整合 = 9 項）
- **Phase 3**：報告 Phase 3（API + 框架 = 7 項）

---

## 2. 策略 Alpha 基準測試（並行任務，不佔開發時間）

> 報告 C.1 指出的最根本風險：「No proven strategy alpha」

**啟動時間：** Phase 0 第一天
**持續時間：** 2 週（與 Phase 0 + Phase 1 並行）
**方法：** 現有 5 個策略 + Batch 9A 已完成的成本感知門檻，固定參數跑 Paper Trading
**不寫任何代碼。** 只是讓系統跑著、記錄結果。

**決策點（Phase 0 結束時，~Day 10）：**

| 基準 PnL | 決策 |
|----------|------|
| > 0（正淨 PnL） | 策略有初步 edge，繼續 Phase 1-3 |
| 約 0（-1% ~ +1%） | 邊際不明，繼續但 Phase 2 策略升級優先級提升 |
| < -3% | 暫緩 Phase 1 新模組，優先用 BacktestEngine 做歷史回測分析失效原因 |

**Operator 行動：** Phase 0 完成後，PM 產出 Alpha 基準報告，Operator 決定是否繼續。

---

## 3. Phase 0 — Batch 9B + 9C + 9D（本週，~5 天壁鐘）

### 3.0 前置條件
- Batch 9A 已完成（commit d9b102f，3703 tests）
- Paper Trading 重啟（Alpha 基準測試開始並行）

### 3.1 Sub-phase 0A — 學習閉環 + 管線連通（Day 1-3）

**目標：** 業務完成度 52% → ~72%

| 任務 | 來源 | 估時 | 依賴 | 並行組 | E1 |
|------|------|------|------|--------|----|
| U-01：學習反饋閉環 | FA P0-GAP-1 | 4h | 無 | A | E1-Alpha |
| U-02：進化參數重部署 | FA P0-GAP-2 | 4h | 無 | A | E1-Beta |
| U-06：H0 Gate shadow 觀察 | FA P1-GAP-3 | 1h | 無 | A | E1-Gamma |
| U-07：Scanner→Deployer | FA P1-GAP-5 | 2h | 無 | A | E1-Delta |
| U-08：Backtest 啟用 | FA P1-GAP-6 | 2h | 無 | A | E1-Epsilon |
| U-15：L2 門檻降低 | FA P2-GAP-7 | 1h | 無 | A | E1-Gamma（第二項） |

**全部可並行（並行組 A）。壁鐘 ~4h + E2 review 2h + E4 回歸 1h = Day 1 完成。**
**Day 2 緩衝：處理 E2 打回的修改。**

**驗收標準：**
- [ ] `_apply_pattern_insight()` 在 `_evaluate_signal()` 路徑中被調用（有端到端測試）
- [ ] EvolutionEngine → Deployer 路徑存在且有治理 gate
- [ ] H0 Gate shadow 模式：記錄 would-have-blocked 計數器但不攔截
- [ ] Scanner scan 完成後通知 Deployer（有集成測試）
- [ ] Backtest 在策略部署前執行，Sharpe < 0 標記警告
- [ ] L2 觸發門檻可配置，默認 20
- [ ] CC 確認：U-02 重部署走 GovernanceHub 審批（原則 3）
- [ ] E4：3703+ 基準不回歸，新增測試 >= 25

### 3.2 Sub-phase 0B — 策略 Edge 驗證（Day 3-5）

**目標：** 原則 9 條件單補全 + FundingRateArb 精算 + Kelly 可視化

| 任務 | 來源 | 估時 | 依賴 | 並行組 | E1 |
|------|------|------|------|--------|----|
| U-10：FundingRateArb 成本模型 | QC S3 | 6h | U-08（Backtest） | B | E1-Alpha |
| U-11：交易所條件單 SL/TP | FA P1-GAP-4 | 6h | 無 | B | E1-Beta |
| U-14：Kelly fraction + GUI | QC S4 | 3h | U-05（已完成） | B | E1-Gamma |

**U-10 依賴 U-08（Sub-phase 0A），其餘可並行。壁鐘 ~6h + E2 2h + E3（U-11 安全）1h + E4 1h = ~Day 4 完成。**

**驗收標準：**
- [ ] FundingRateArb 成本模型文檔化（手續費+滑點+funding rate+basis risk+持倉天數）
- [ ] Bybit Demo 側開倉後存在 SL/TP 條件單
- [ ] Kelly fraction 在 tab-ai.html 顯示，不足 50 筆顯示 "N/A"
- [ ] Agent 根據 Kelly 自動分配資本（Operator 決策 2026-04-02）
- [ ] E3 安全審查：條件單 API 調用無注入風險
- [ ] E4：新增測試 >= 15

### Phase 0 交付物
- commit（所有代碼 + TODO.md + CLAUDE.md）
- Alpha 基準測試開始 ~10 天後的中期報告
- 業務完成度從 ~52% → ~72%

---

## 4. Phase 1 — Agent 感知工具箱（Week 2-3，~5 天壁鐘）

### 4.0 前置條件
- Phase 0 完成（commit + E2 + E4 通過）
- Alpha 基準測試持續運行中

### 4.1 Sub-phase 1A — 核心感知工具（Day 1-3）

報告並行依賴圖 Group A + 1.5：

| 任務 | 來源 | 估時 | 依賴 | 並行組 | 說明 |
|------|------|------|------|--------|------|
| 1.1 PositionSizer | 報告 §5.1 | 1d | 無 | A | Kelly 四層倉位計算（U-14 的增強版） |
| 1.2 StrategyHealthMonitor | 報告 §5.2 | 1d | 無 | A | CUSUM 策略衰減檢測 + 硬性兜底 |
| 1.3 EWMAVolEstimator | 報告 §5.3 | 0.5d | 無 | A | 按時間框架調整 lambda |
| 1.4 Hurst 計算 | 報告 §5.4 | 0.5d | 無 | A | R/S 分析，趨勢/均回判斷 |

**Group A 全部可並行。壁鐘 ~1d。**

| 任務 | 來源 | 估時 | 依賴 | 並行組 | 說明 |
|------|------|------|------|--------|------|
| 1.5 Indicator Engine 擴展 | 報告 §6.6 | 1.5d | 1.3, 1.4 接口 | B | KAMA, ADX, Hurst, EWMA Vol, Volume Ratio, Donchian |

**1.5 依賴 Group A 的接口定義（非完整實現），壁鐘 Day 2-3。**

### 4.2 Sub-phase 1B — 整合工具（Day 3-5）

報告並行依賴圖 Group B + 1.9：

| 任務 | 來源 | 估時 | 依賴 | 並行組 | 說明 |
|------|------|------|------|--------|------|
| 1.8 LocalLLMClient 抽象 | 報告 §4.5 | 0.5d | 無 | C | ABC 接口，兼容 Ollama + LM Studio |
| 1.9 影子決策追踪 | 報告 §2 | 0.5d | 1.2（HealthMonitor） | C | 四階段退出條件的數據基礎 |

**Group C 可並行。壁鐘 ~0.5d。**

**E2 + E4：Day 4-5。**

### Phase 1 驗收標準
- [ ] PositionSizer.compute_recommendation() 返回 kelly_qty / vol_qty / max_qty
- [ ] StrategyHealthMonitor.get_health_data() 返回 cusum_detected 字段
- [ ] EWMAVolEstimator.get_vol_regime() 返回 high/normal/low
- [ ] compute_hurst_exponent() 返回 0-1 浮點，0.60/0.40 為判斷閾值
- [ ] IndicatorEngine 新增 6 個指標（KAMA, ADX, Hurst, EWMA Vol, Volume Ratio, Donchian）
- [ ] LocalLLMClient ABC 實現，OllamaLLMClient 適配現有代碼
- [ ] 影子決策追踪：shadow vs actual 差異記錄
- [ ] 所有新模組有 get_schema() + get_alerts()（報告 §1 規範）
- [ ] 所有新模組零 live import（原則 7 隔離）
- [ ] E4：新增測試 >= 40（每模組 >= 5）

### Phase 1 session 上下文

**必讀文件（最小集）：**
1. `CLAUDE.md` §三（系統狀態）+ §六（硬邊界）+ §十四（代碼結構約定）
2. `TODO.md`（確認 Phase 0 已完成，找到 Phase 1 起點）
3. `docs/references/2026-04-03--openclaw_improvement_report_v3_final.md` §5（模組代碼定義）+ §6.6（Indicator 擴展）
4. `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-03--unified_execution_roadmap.md`（本文件，Phase 1 段）
5. 已有相關文件：`program_code/local_model_tools/indicator_engine.py`（擴展目標）
6. 已有相關文件：`app/strategist_agent.py`（PositionSizer 注入點）
7. 已有相關文件：`app/analyst_agent.py`（HealthMonitor 注入點）

**不需要讀：** Batch 9A-9D 的詳細設計（已完成），Wave 0-8 歷史記錄，審計報告。

---

## 5. Phase 2 — 策略升級 + Agent 整合（Week 3-5，拆為 2 個 sub-phase，~10 天壁鐘）

### 5.0 前置條件
- Phase 1 完成
- Alpha 基準測試 2 週結果已出 → Operator 已確認繼續

**重要：若 Alpha 基準 PnL < -3%，Phase 2 轉為「策略研究 Sprint」而非「策略升級 Sprint」。**
具體轉換方案見 §8.2。

### 5.1 Sub-phase 2A — 策略 V2 第一批（Day 1-5）

| 任務 | 來源 | 估時 | 依賴 | 並行組 | 說明 |
|------|------|------|------|--------|------|
| 2.1 MA_Crossover V2 | 報告 §6.1 | 3d | 1.5（KAMA, ADX） | D | 3 步驗證：KAMA + ADX>20 + 多時間框架 |
| 2.2 BB_Reversion V2 | 報告 §6.2 | 1.5d | 1.5, 1.3 | D | RSI<30 + Regime 感知 + Limit order |
| 2.3 BB_Breakout V2 | 報告 §6.3 | 1.5d | 1.5 | D | Volume ratio>1.5 + ATR trailing + Donchian 確認 |

**2.1/2.2/2.3 可並行。壁鐘 ~3d。**

| 任務 | 來源 | 估時 | 依賴 | 說明 |
|------|------|------|------|------|
| 2.6 Regime Detection 升級 | 報告 | 2d | 1.3（EWMA）, 1.4（Hurst） | 整合 Hurst + EWMA Vol 進 regime_detector |

**2.6 可與 2.1-2.3 並行（不同文件）。**

**E2 + E4：Day 4-5。**

### 5.2 Sub-phase 2B — Agent 整合 + 剩餘策略（Day 6-10）

| 任務 | 來源 | 估時 | 依賴 | 並行組 | 說明 |
|------|------|------|------|--------|------|
| 2.4 FundingRateArb V2 | 報告 §6.4 | 4d | U-10（Phase 0）| E | 雙腿 Paired Execution + Basis |
| 2.5 GridTrading V2 | 報告 §6.5 | 1.5d | 1.3（EWMA） | E | OU 動態間距 + 成本修正 |
| 2.7 Strategist 雙軌 + 優先級隊列 | 報告 §3.3 | 2d | 無 | E | 快速通道 + 正常通道 + emergency_mode |
| 2.8 ContextDistiller | 報告 §4.2 | 1d | 無 | E | 壓縮系統狀態為 ~450 tokens |
| 2.9 Strategist/Analyst prompt 模板 | 報告 | 1.5d | 2.7 | F | JSON 結構化 prompt + reasoning 強制 |

**並行：2.4/2.5/2.7/2.8 可同時進行（不同文件/模組）。2.9 依賴 2.7。**

**E2 + E4 + E3（2.4 Paired Execution 安全審查）：Day 9-10。**

### Phase 2 驗收標準
- [ ] MA_Crossover V2：KAMA 替代 EMA + ADX>20 過濾 + 多時間框架
- [ ] BB_Reversion V2：RSI<30 確認 + regime=trending 時不開倉
- [ ] BB_Breakout V2：Volume ratio>1.5 確認 + Donchian 確認信號
- [ ] FundingRateArb V2：Paired Execution + 回滾（基於 filled_qty）
- [ ] GridTrading V2：OU 間距 >= sigma/sqrt(theta) + 2*fee_pct
- [ ] Strategist 雙軌：快速通道 MappingProxyType 不可變 + emergency_mode 原子標誌
- [ ] ContextDistiller：threading.Lock + deepcopy + ~450 tokens 輸出
- [ ] Prompt 模板：結構化 JSON + 強制 reasoning 字段
- [ ] 每個升級策略獨立跑 Paper 2 週（非阻塞）
- [ ] E4：新增測試 >= 60

### Phase 2 session 上下文

**必讀文件：**
1. `CLAUDE.md` §三 + §六 + §十四
2. `TODO.md`（Phase 1 完成確認）
3. `docs/references/2026-04-03--openclaw_improvement_report_v3_final.md` §3（Agent 決策流程）+ §6（策略升級）+ 附錄 B.1.1/B.1.3（競態/回滾）
4. 本文件 Phase 2 段
5. Phase 1 新建的模組文件（PositionSizer, HealthMonitor, EWMA, Hurst, Indicator Engine 擴展）
6. 已有策略文件：`program_code/local_model_tools/strategies/`
7. `app/strategist_agent.py` + `app/multi_agent_framework.py`

---

## 6. Phase 3 — API 整合 + 框架（Week 5-7，拆為 2 個 sub-phase，~8 天壁鐘）

### 6.0 前置條件
- Phase 2 完成
- 策略 V2 Paper Trading 觀察中

### 6.1 Sub-phase 3A — Claude API + 路由（Day 1-4）

| 任務 | 來源 | 估時 | 依賴 | 並行組 | 說明 |
|------|------|------|------|--------|------|
| 3.1 Claude API 客戶端 + APIBudgetManager | 報告 §4.4 | 1.5d | 無 | G | 月度預算 + 持久化 + 冷卻期 |
| 3.2 L1→L2 路由邏輯 | 報告 §4.1 | 1d | 3.1 | H | L0/L1/L1.5/L2 四層路由條件 |
| 3.3 Claude→TSR 閉環 | 報告 §4.3 | 1d | 3.1, 3.2 | H | knowledge_update → TSR + audit_log |
| 3.5 PnLAttributor + API + GUI | 報告 §5.6 | 2d | 無 | G | 策略/幣種/時段 PnL 分解 |

**3.1 和 3.5 可並行。3.2/3.3 依賴 3.1。壁鐘 ~3d + E2/E4 1d。**

### 6.2 Sub-phase 3B — 高級功能（Day 5-8）

| 任務 | 來源 | 估時 | 依賴 | 並行組 | 說明 |
|------|------|------|------|--------|------|
| 3.4 HedgingEngine | 報告 §5.5 | 1.5d | 無 | I | delta 計算 + 對沖建議（只讀工具） |
| 3.6 OB Imbalance + Orderbook WS | 報告 | 2d | 無 | I | orderbook.1 (100ms) 減 CPU |
| 3.7 四階段框架（GovernanceHub 持久化） | 報告 §2 | 2d | Phase 0-2 全部 | I | 階段升降級 + 磁盤持久化 + 重啟恢復 |

**3.4/3.6/3.7 可並行。壁鐘 ~2d + E2/E4/E3 2d。**

### Phase 3 驗收標準
- [ ] Claude API 客戶端：Sonnet(L1.5) + Opus(L2) 路由正確
- [ ] APIBudgetManager：月度重置 + 磁盤持久化 + 冷卻期
- [ ] L1→L2 升級條件全部實現（6 條升級 + 3 條阻止）
- [ ] Claude→TSR：knowledge_update 寫入帶 TTL + source="cloud_api"
- [ ] PnLAttributor：by_strategy/by_symbol/by_hour 三維分解
- [ ] HedgingEngine：delta 計算 + benefit/cost ratio 建議
- [ ] OB Imbalance：orderbook.1 WS 接入 + 不平衡度計算
- [ ] 四階段：階段 1-4 升降級邏輯 + 持久化 + 重啟恢復 + 自動降級
- [ ] E4：新增測試 >= 50

### Phase 3 session 上下文

**必讀文件：**
1. `CLAUDE.md` §三 + §六 + §十四
2. `TODO.md`
3. `docs/references/2026-04-03--openclaw_improvement_report_v3_final.md` §2（四階段）+ §4（L0-L2）+ §5.5/5.6（HedgingEngine/PnLAttributor）
4. 本文件 Phase 3 段
5. `app/governance_hub.py`（四階段持久化注入點）
6. `app/layer2_engine.py`（L1→L2 路由注入點）
7. Phase 1/2 新建的模組

---

## 7. Phase 4 — 條件性（報告 Phase 4，不定期）

以下任務有明確前置條件，非定期排程：

| 任務 | 前置條件 | 估時 |
|------|---------|------|
| 4.1 PairsTrading | 3 月歷史協整穩定性驗證 | 待定 |
| 4.2 Beta Hedging | HedgingEngine 穩定 1 月 | 待定 |
| 4.3 Kalman Filter | KAMA 表現不理想（Phase 2 之後評估） | 待定 |
| 4.4 JSON→PostgreSQL | 數據量瓶頸（當前未觸及） | 待定 |
| 4.5 Mac Studio 遷移 | 硬件到手 | 待定 |

加上 Batch 9 延後項：

| 任務 | 前置條件 |
|------|---------|
| U-12 統計適應硬門檻 | 200+ trades/regime |
| U-13 參數空間 step | U-12 |
| U-16 Walk-forward harness | 6+ 月 K 線數據 |
| U-17 Deflated Sharpe Ratio | U-16 |
| U-18 Jump detection | 改進項，非阻塞 |

---

## 8. 風險管理

### 8.1 報告提到的三大風險

#### 風險 1：No proven strategy alpha（最根本）

**緩解：** Alpha 基準測試從 Day 1 並行啟動。Phase 0 結束時（~Day 10）出第一份報告。

**決策點：**
- Day 10：Alpha 基準中期報告 → Operator 決定是否繼續
- Day 20：Alpha 基準最終報告 → Phase 2 是否轉為「策略研究」

#### 風險 2：複雜度稅（~10 新模組維護負擔）

**緩解：**
- 每個模組必須是只讀工具（無副作用），降低交互 debug 成本
- 模組 <800 行（§14.1 警告線），超過必須拆分
- 每個模組有 get_schema() 自描述，降低認知負擔
- Phase 結束時做模組數量 vs 測試數量 vs bug 數量的比率分析

**量化追蹤：**
- Phase 0 結束：~0 新模組（管線接通，不新建模組）
- Phase 1 結束：+5 新模組（PositionSizer, HealthMonitor, EWMA, Hurst, LLMClient）
- Phase 2 結束：+3 新模組（ContextDistiller, PairedExecution, PromptTemplates）+ 5 策略修改
- Phase 3 結束：+4 新模組（APIClient, PnLAttributor, HedgingEngine, OBImbalance）+ 1 框架修改

總計：~12 新模組。風險在可控範圍內，但超過 15 個需要暫停評估。

#### 風險 3：開發過長造成脫節

**緩解：** 5 天切分規則（見 §9）。每個 sub-phase 有獨立 commit + E2 + E4。新 session Agent
讀最小上下文集，不需要讀完整歷史。

### 8.2 Alpha 基準失敗的備選方案

若 Alpha PnL < -3%，Phase 2 從「策略升級」轉為：

```
Phase 2-ALT：策略 Alpha 研究（~2 週）
  1. 用 BacktestEngine 做 6 個月歷史回測（Phase 0 U-08 已啟用）
  2. 用 L2 Claude API 分析策略失效原因（Phase 3 提前抽出 3.1）
  3. 重新設計策略假設 → ExperimentLedger 提交 → Paper 驗證
  4. 若仍無 edge → Operator 決定是否轉為純 Funding Rate 策略
```

---

## 9. 切分規則（所有 Phase 強制遵守）

### 9.1 時間硬約束

| 規則 | 約束 |
|------|------|
| 單 sub-phase 壁鐘上限 | 5 天（含 E2+E4） |
| 超過 5 天的 sub-phase | 必須再拆 |
| 每個 sub-phase 結束必須有 | commit + E2 通過 + E4 回歸通過 |
| Phase 之間的間隔 | 至少 1 天（消化 E2 反饋 + 更新文檔） |

### 9.2 每個 Sub-phase 的強制交付物

1. **代碼 commit**：生產代碼 + 測試 + TODO.md + CLAUDE.md
2. **E2 審查通過**：無 MUST-FIX 殘留
3. **E4 回歸通過**：基準不回歸 + 新增測試達標
4. **CLAUDE.md §三 更新**：反映最新完成狀態

### 9.3 新 Session Agent 上下文規則

每個 Phase/sub-phase 由獨立 Claude Code session 執行。上下文文件分三層：

**Layer 0（必讀，所有 session）：**
- `CLAUDE.md`（§三狀態 + §六硬邊界 + §十四代碼約定）
- `TODO.md`（找到當前起點）
- 本文件對應 Phase 段

**Layer 1（Phase 專屬）：**
- 該 Phase 的參考文件（見各 Phase「session 上下文」節）

**Layer 2（按需）：**
- 僅在修改特定文件時讀取該文件
- 不讀已完成 Phase 的詳細設計/報告

**原則：讀最少夠用的文件，不讀重複歷史。**

---

## 10. 時間線總覽

```
          Week 1          Week 2          Week 3          Week 4          Week 5          Week 6          Week 7
         ┌──────┐        ┌──────┐        ┌──────┐        ┌──────┐        ┌──────┐        ┌──────┐        ┌──────┐
Alpha:   │████████████████████████████████│ Day 10 報告    │ Day 20 最終報告 │                              │
         │        並行 Paper Trading      │ → Operator 決策│                │                              │
         └──────┘        └──────┘        └──────┘        └──────┘        └──────┘        └──────┘        └──────┘

Phase 0: │██ 0A ██│██ 0B ██│ buffer │
         │ 學習+管線│ 策略Edge│        │
                                       
Phase 1:                  │██ 1A ██│██ 1B ██│ buffer │
                          │ 感知工具 │ 整合   │        │

Phase 2:                                     │████ 2A ████│████ 2B ████│ buffer │
                                             │ 策略 V2    │ Agent 整合 │        │

Phase 3:                                                                │██ 3A ██│██ 3B ██│ buffer │
                                                                        │ API    │ 高級   │        │

決策點:            ☆ Phase 0 完成            ☆ Alpha 報告   ☆ Phase 2 完成
                   (繼續/暫停?)              (繼續/轉研究?)  (Phase 3 啟動?)
```

---

## 11. 里程碑與決策點

| 時間點 | 里程碑 | 決策 | 決策者 |
|--------|--------|------|--------|
| Day 5 | Phase 0 完成 | 業務完成度達 ~72%？ | PM 確認 |
| Day 10 | Alpha 基準中期報告 | PnL 方向判斷 | Operator |
| Day 15 | Phase 1 完成 | 5 新模組全部可用？ | PM + E4 確認 |
| Day 20 | Alpha 基準最終報告 | Phase 2 策略升級 or 策略研究？ | Operator |
| Day 30 | Phase 2 完成 | 策略 V2 Paper 表現？是否啟動 Phase 3？ | Operator |
| Day 40 | Phase 3 完成 | 四階段框架啟用？Claude API 接入？ | Operator |
| Day 60+ | Paper Trading 21 天觀察期結束 | 準備 Supervised Live？ | Operator |

**「是否值得繼續」的第一個決策點：Day 10（Alpha 中期報告）。**
如果策略明顯無 edge（PnL < -3%），立即暫停新模組開發，轉入策略研究。

---

## 12. 與 Operator 決策的對應

| Operator 決策（2026-04-02） | 本計劃對應 |
|------------------------------|-----------|
| 成本門檻不能造成零成交 | Batch 9A 已完成（commit d9b102f），cost_gate fail-open + 每日安全閥 |
| Paper/Demo 自動重部署免確認 | Phase 0 U-02：EvolutionEngine→Deployer 路徑，Paper/Demo 免確認 |
| H0 Gate shadow 觀察 1 週再切 blocking | Phase 0 U-06：shadow 模式，Phase 1 結束後評估是否切 blocking |
| 策略資本分配交給 Agent 根據 Kelly 自動決定 | Phase 0 U-14 + Phase 1 PositionSizer：Kelly→Agent 自主分配 |

---

## 13. 附錄：報告「明確不做」項目確認

以下報告 §8 列出的項目，本計劃亦不做：

| 不做項目 | 理由 | PM 確認 |
|---------|------|---------|
| HMM Regime | 過擬合，crypto regime 切換太快 | 同意 |
| GARCH | 跳躍太多，EWMA 更穩健 | 同意 |
| VPIN | 中頻系統預測價值低 | 同意 |
| 波動率均值回歸策略 | 需期權，Bybit 流動性差 | 同意 |
| Donchian/VolBreakout 獨立策略 | 降為 BB_Breakout 確認信號 | 同意 |
| Guardian 寫權限 | 架構決策不變 | 同意 |
| Binance | 專攻 Bybit | 同意 |

---

> PM (Project Manager)
> 2026-04-03
> 本文件為所有後續開發的主計劃文件。Phase 開始前需 Operator 確認。
