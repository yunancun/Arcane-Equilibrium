# FA 報告：外部改善報告 vs 現有系統 GAP 對比
# FA Report: Improvement Report V3 vs Current System Gap Comparison

> 審查人：FA（Functional Auditor）
> 日期：2026-04-03
> 基於：
>   - 改善報告：`docs/references/2026-04-03--openclaw_improvement_report_v3_final.md`
>   - FA GAP 審計：`docs/governance_dev/audits/2026-04-01--fa_completion_gap_audit.md`
>   - Batch 9A 規格：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-04-02--adaptive_params_functional_spec.md`

---

## 1. 功能重疊分析

| 報告任務 | Phase | 我們的對應 | 重疊度 | 說明 |
|---------|-------|-----------|--------|------|
| 1.6 學習反饋迴路修復 | 1 | FA P0-GAP-1（學習反饋閉環斷開） | **100%** | 完全相同問題：TSR→Strategist `_apply_pattern_insight()` 從未被調用 |
| 1.7 Evolution→Deploy 連接 | 1 | FA P0-GAP-2（進化參數不自動重部署） | **100%** | 完全相同：EvolutionEngine→Deployer 無交叉引用。Wave 8B 已做初步連接但未完整 |
| 1.1 PositionSizer | 1 | 現有動態 qty（Wave 5a） | **50%** | 我們有 risk/stop 反推 qty，但缺 Kelly、Risk Parity、Volatility Adjusted 三層。報告的 4 層設計更完整 |
| 1.2 StrategyHealthMonitor | 1 | 無直接對應 | **30%** | 我們有 StrategyAutoDeployer 自動暫停（連虧閾值），但無 CUSUM 衰減檢測、無滾動 Sharpe/WR 監控 |
| 1.3 EWMAVolEstimator | 1 | 無 | **10%** | 我們有 ATR，但無 EWMA 波動率估計器。RegimeDetectorRule 有簡單 vol 分類但非 EWMA |
| 1.4 Hurst 計算 | 1 | 無 | **0%** | 全新。我們沒有 Hurst Exponent，regime 判斷靠 ATR+BB+EMA |
| 1.5 Indicator Engine 擴展（6 指標） | 1 | Batch 9A 部分覆蓋 | **40%** | 我們計劃加 ATR(5)。報告要加 KAMA/ADX/Hurst/EWMA/VolumeRatio/Donchian 共 6 個 |
| 1.8 LocalLLMClient 抽象 | 1 | 現有 OllamaClient | **30%** | 我們有 Ollama 專用客戶端。報告要 ABC 抽象支持 Ollama+LMStudio，更通用 |
| 1.9 影子決策追踪 | 1 | 無 | **20%** | 我們有 shadow=False 切換歷史，但無系統化的「影子決策 vs 實際決策」比對機制 |
| 2.1 MA_Crossover V2 | 2 | 無計劃 | **0%** | KAMA+ADX+多時間框架確認，全新升級 |
| 2.2 BB_Reversion V2 | 2 | 無計劃 | **0%** | RSI<30 確認+Regime 感知+Limit order |
| 2.3 BB_Breakout V2 | 2 | 無計劃 | **0%** | Volume ratio+ATR trailing+Donchian 確認 |
| 2.4 FundingRateArb V2 + Paired Execution | 2 | Batch 9A-E（FundingArb 成本模型） | **40%** | 我們計劃加 funding 歷史+basis risk。報告額外要 Paired Execution（雙腿同步+回滾） |
| 2.5 GridTrading V2 | 2 | 無計劃 | **0%** | OU 動態間距 + 趨勢偏移 |
| 2.6 Regime Detection 升級 | 2 | Batch 9A-C（Regime-aware 參數映射） | **50%** | 我們計劃統一 regime→風控映射。報告要加 Hurst+EWMA 到 regime 判斷本身 |
| 2.7 Strategist 雙軌+優先級隊列 | 2 | 無 | **0%** | 全新：快速通道（L0 確定性規則）+ 正常通道（L1 Ollama 優先級隊列） |
| 2.8 ContextDistiller | 2 | 無 | **0%** | 全新：壓縮系統狀態為 ~450 tokens 摘要給 API 調用 |
| 2.9 Prompt 模板 | 2 | 部分 | **30%** | 我們 Strategist 有基本 prompt，但非結構化 JSON 強制格式 |
| 3.1 Claude API 客戶端+APIBudgetManager | 3 | 現有 L2 Engine（layer2_engine.py） | **40%** | 我們有 L2 成本追踪（Layer2CostTracker），但無月度預算管理、無持久化、無冷卻期 |
| 3.2 L1→L2 路由邏輯 | 3 | H3 ModelRouter | **60%** | 我們有 complexity-based 三層路由（L1 9B/27B/L2）。報告加了 L1.5（Sonnet）和更精細的升級條件 |
| 3.3 Claude→TSR 閉環 | 3 | 部分 | **40%** | 我們有 L2→AnalystAgent 路徑，但 Claude 回答不直接寫 TSR |
| 3.4 HedgingEngine | 3 | 無 | **0%** | 全新：Delta 計算+對沖建議 |
| 3.5 PnLAttributor | 3 | 部分 | **20%** | 我們有 round-trip PnL 記錄，但無按策略/幣種/時段的歸因分解 |
| 3.6 OB Imbalance+Orderbook WS | 3 | 無 | **0%** | 全新：訂單簿不平衡檢測 |
| 3.7 四階段放權框架 | 3 | 無 | **0%** | 全新：量化條件升降級機制（詳見 §2 獨有功能分析） |

---

## 2. 報告獨有的功能（我們沒有也沒計劃的）

### 2.1 四階段遞進式放權框架（§2）— 建議 P1 採納

**內容**：4 個階段（監控→P2 調參→完整 P2→策略創造），每階段有量化進入條件（Sharpe/WR/DD/筆數）和自動回退觸發。

**評估**：
- **值得做**：這填補了我們 PaperLiveGate（11 項準入）和 SM-01 授權之間的巨大空白。我們目前只有「demo_only / live」二態，沒有漸進放權。
- 與我們的「Phase 4: Paper Trading 觀察 + Live 準備」高度互補。
- **建議**：Phase 4 啟動時實作。不急，因為當前 system_mode=demo_only，但進 live 前必須有。
- **工時**：2-3 天（GovernanceHub 擴展 + 持久化 + 條件評估）

### 2.2 Strategist 雙軌機制 + 快速通道（§3.3）— 建議 P1 採納

**內容**：
- 快速通道（L0，<10ms）：Risk Governor >= DEFENSIVE 時觸發預定義規則（reduce_all/close_all/flash_crash/margin_critical），使用 `MappingProxyType` 保護不可修改。
- 正常通道（L1，2-8s）：優先級隊列（P1 平倉 > P2 對沖 > P3 新開 > P4 調參）。

**評估**：
- **值得做**：我們的 RiskManager `_check_stops()` 有類似緊急平倉邏輯，但分散在多處且不是統一快速通道。集中化後更易審計。
- 優先級隊列在高壓力時（25 symbol 同時有信號）非常有用。
- **建議**：P1，與策略升級同批次做。
- **工時**：2 天

### 2.3 L1.5 層（Claude Sonnet API）— 建議 P2 暫緩

**內容**：在 L1（Ollama）和 L2（Opus）之間加一層 Sonnet，用於跨策略仲裁、Regime 確認、中等回撤分析。~$0.02/次。

**評估**：
- **暫不需要**：我們的 H3 ModelRouter 已做 9B/27B/L2 三層路由。27B 本地模型 ~9.9s 可覆蓋 L1.5 的大部分場景。
- 額外 API 成本與原則 14（零外部成本可運行）有張力。
- **建議**：P2，等 27B 本地表現不足時再引入。或等硬件升級（72B）後重新評估。

### 2.4 ContextDistiller — 建議 P1 採納

**內容**：壓縮系統狀態為 ~450 tokens 摘要，API 調用時只發摘要+問題，減少 token 成本。

**評估**：
- **值得做**：我們目前 L2 調用把大量原始數據塞進 prompt，token 浪費嚴重。
- 實現簡單（純只讀壓縮），無副作用風險。
- **建議**：與 APIBudgetManager 一起做。
- **工時**：0.5-1 天

### 2.5 APIBudgetManager（§4.4）— 建議 P1 採納

**內容**：月度預算管理，持久化到磁盤，冷卻期，月重置。

**評估**：
- **值得做**：我們的 Layer2CostTracker 有 daily cap（$2）但無月度預算管理、無持久化（重啟歸零）。
- 與原則 13（AI 資源成本感知）強相關。
- **建議**：P1，擴展現有 Layer2CostTracker。
- **工時**：0.5 天（已有骨架，加持久化+月重置）

### 2.6 Paired Execution（§3.5）— 建議 P2

**內容**：FundingRateArb 的雙腿同步提交，第一腿成功+第二腿失敗→回滾第一腿，回滾失敗→INCIDENT。

**評估**：
- **值得做但複雜**：FundingRateArb 是唯一需要雙腿的策略，目前 Paper Engine 沒有原子性雙腿機制。
- 回滾邏輯涉及 Demo connector 改動，風險較高。
- **建議**：P2，在 FundingRateArb V2 中一起做。
- **工時**：4 天（報告估計，含回滾+錯誤處理）

### 2.7 PositionSizer 四層（§5.1）— 建議 P1

**內容**：Kelly Fraction（根據樣本量折扣：1/8→1/6→1/4）+ Volatility Adjusted + Risk Parity + P1 硬上限。只讀工具，Strategist 參考。

**評估**：
- **值得做**：我們的 qty 計算只有 risk/stop 反推一種方式。Kelly 和 Risk Parity 提供多維度參考。
- 純只讀工具，無副作用，低風險。
- **建議**：P1，Phase 1 基礎模組。
- **工時**：1 天

### 2.8 StrategyHealthMonitor + CUSUM（§5.2）— 建議 P1

**內容**：滾動 Sharpe/WR + CUSUM 衰減檢測 + 15 連虧硬性暫停。

**評估**：
- **值得做**：我們有 StrategyAutoDeployer 的簡單暫停（連虧觸發），但無 CUSUM。CUSUM 比固定連虧閾值更早發現策略衰減。
- 四階段放權框架的退出條件依賴此模組。
- **建議**：P1。
- **工時**：1 天

### 2.9 EWMAVolEstimator + HurstExponent（§5.3-5.4）— 建議 P1

**評估**：
- EWMA Vol：比 ATR 更適合即時波動率估計，可輸入 Risk Governor 動態調整。
- Hurst：區分趨勢/均值回歸/隨機，比現有 ATR+BB 方法更有統計學基礎。
- 兩者都是只讀工具，實現簡單。
- **建議**：P1，一起做。
- **工時**：共 1 天

### 2.10 HedgingEngine（§5.5）— 建議 P3

**評估**：
- 功能有意義（Delta 計算+對沖建議），但前置條件是持倉量足夠大到需要對沖。
- 當前 demo 階段、25 symbol 上限，組合風險不大。
- **建議**：P3，live 後再考慮。

### 2.11 PnLAttributor（§5.6）— 建議 P2

**評估**：
- 按策略/幣種/時段歸因 PnL，對理解哪個策略在何時賺錢極有價值。
- 我們有 round-trip 記錄但無歸因分解。
- **建議**：P2，學習系統擴展時做。
- **工時**：1 天

### 2.12 OB Imbalance + Orderbook WS（§5.6, §9）— 建議 P3

**評估**：
- 訂單簿深度對中頻系統價值有限（報告自己在 §8 也暗示 VPIN 價值低）。
- WS 連接增加系統複雜度。
- **建議**：P3，條件性。

### 2.13 策略 V2 升級（§6 全部 5 個策略）— 建議 P2 分步

**評估**：
- MA_Crossover V2（KAMA+ADX+多時間框架）：最有價值，趨勢策略是主力
- BB_Reversion V2（RSI+Regime）：中等價值
- BB_Breakout V2（Volume+ATR+Donchian）：中等價值
- FundingRateArb V2：與 Batch 9A-E 重疊
- GridTrading V2（OU 動態間距）：中等價值
- **建議**：P2，按報告建議每策略獨立 Paper Trade 2 週驗證。先做 MA_Crossover V2。

### 2.14 LLM 客戶端抽象（§4.5）— 建議 P3

**評估**：
- 目前只用 Ollama，LM Studio 支持是為未來硬件擴展準備。
- 抽象層增加間接性，當前無即時需求。
- **建議**：P3，硬件升級時做。

---

## 3. 設計差異（同一功能，不同實現方式）

### 3.1 學習反饋路徑

| 方面 | 我們的設計 | 報告設計 | 建議 |
|------|-----------|---------|------|
| TSR→策略注入 | `_apply_pattern_insight()` 調整 confidence | TSR insights 注入 `_make_shadow_decision()` 的 confidence 調整 | **採用報告**：在決策路徑而非事後調用更合理 |
| AI 回答處理 | L2→AnalystAgent 消費 | Claude→TSR 直接寫入 `knowledge_update`（帶 TTL+source） | **採用報告**：更直接，減少中間環節 |

### 3.2 Model Router 層級

| 方面 | 我們的設計 | 報告設計 | 建議 |
|------|-----------|---------|------|
| 層數 | 3 層：L1-9B / L1-27B / L2-Claude | 4 層：L0 / L1 / L1.5-Sonnet / L2-Opus | **保持我們的** 3 層，暫不加 L1.5（原則 14） |
| 升級條件 | complexity score | 6 個量化條件（confidence+金額+Sharpe+波動+幣種+PnL） | **採用報告**：更精細的升級條件值得移植 |
| 阻止條件 | H2 budget gate | 3 個阻止條件（冷卻+快速通道+月預算） | **採用報告**：比我們的更完整 |

### 3.3 風控 Regime 感知

| 方面 | 我們的設計（Batch 9A） | 報告設計 | 建議 |
|------|----------------------|---------|------|
| Regime 來源 | RegimeDetectorRule（ATR+BB+EMA） | 加 Hurst+EWMA 到 regime 判斷 | **合併**：保留現有基礎，加 Hurst/EWMA 作為確認信號 |
| Regime→風控映射 | `REGIME_ATR_MULTIPLIERS` 代碼常量 | 同樣是確定性映射 | **無衝突**，方向一致 |
| 動態搜索 | QC 明確禁止（<200 trades） | 報告同意不做 | **一致** |

### 3.4 ATR 止損

| 方面 | Batch 9A 規格 | 報告設計 | 建議 |
|------|-------------|---------|------|
| ATR 窗口 | 雙窗口 ATR(5)+ATR(14) 取 max | 未特別提及 ATR 窗口 | **保持 Batch 9A**：QC 審查過的設計更嚴謹 |
| 追蹤止損公式 | 成本感知公式（activation-distance > c_round_pct） | ATR trailing stop 但無成本約束 | **保持 Batch 9A**：成本陷阱修復是 QC M1 級別必修 |
| ATR 倍數 | `ATRMultipliers` dataclass + Operator bounds | 未有同等精度的倍數設計 | **保持 Batch 9A** |

### 3.5 Conductor 角色

| 方面 | 我們的實現 | 報告設計 | 建議 |
|------|-----------|---------|------|
| 現狀 | Conductor 有 dispatch_to_agent()+get_agent_health()（Batch 7），但編排邏輯薄弱 | Conductor 讀 MARKET_ASSESSMENT → 推理策略權重 → 發 STRATEGY_DIRECTIVE | **採用報告**：Conductor 應該是策略權重分配者，而非簡單 dispatcher |

---

## 4. 報告「明確不做」(§8) 與我們計劃的衝突

| 報告不做的項目 | 我們有計劃做嗎 | 衝突 |
|---------------|---------------|------|
| HMM Regime | 無（代碼庫無任何 HMM 引用） | **無衝突** |
| GARCH | 無 | **無衝突** |
| VPIN | 無 | **無衝突** |
| 波動率均值回歸 | 無（需期權，Bybit 流動性差） | **無衝突** |
| Donchian 獨立策略 | 無（報告降為 BB_Breakout 確認信號，合理） | **無衝突** |
| Guardian 寫權限 | 無（我們的 Guardian 也是只審批不修改） | **無衝突** |
| Binance 相關 | 無（專攻 Bybit） | **無衝突** |

**結論：零衝突。** 報告的「不做」清單與我們的計劃完全一致。我們從未計劃做這些，代碼庫中也無相關實現。

---

## 5. 綜合建議：整合路線圖

### 優先級排序（合併 FA GAP + 報告 + Batch 9A）

**立即做（已在計劃中，報告確認方向正確）：**
1. P0-GAP-1 + 報告 1.6：學習反饋閉環接通（採用報告的決策路徑注入方式）
2. P0-GAP-2 + 報告 1.7：Evolution→Deploy 連接
3. Batch 9A 全部（ATR 雙窗口 + 成本感知 + Regime 映射 + 追蹤止損修復 + FundingArb）

**Phase 1 新增（從報告採納，P1）：**
4. PositionSizer 四層（報告 1.1）— 只讀工具，1 天
5. StrategyHealthMonitor + CUSUM（報告 1.2）— 只讀工具，1 天
6. EWMAVolEstimator + Hurst（報告 1.3+1.4）— 只讀工具，1 天
7. ContextDistiller + APIBudgetManager 擴展（報告 2.8+3.1）— 1 天
8. Strategist 快速通道（報告 2.7 的 L0 部分）— 2 天
9. Conductor 策略權重分配升級 — 1 天

**Phase 2 新增（P2）：**
10. MA_Crossover V2（報告 2.1）— 3 天，Paper 2 週驗證
11. 其他策略 V2（報告 2.2-2.5）— 各 1.5-4 天
12. Paired Execution（報告 2.4）— 4 天
13. PnLAttributor（報告 3.5）— 1 天
14. L1→L2 升級條件精細化（報告 3.2）— 1 天

**Phase 3/4 / 條件性：**
15. 四階段放權框架（報告 §2）— live 前必須，2-3 天
16. L1.5 Sonnet 層 — 等 27B 本地不足時
17. HedgingEngine — live + 大倉位後
18. OB Imbalance — 條件性
19. LLM 客戶端抽象 — 硬件升級時

### 與現有 FA GAP 的完整對照

| FA GAP # | 報告是否涵蓋 | 合併策略 |
|----------|-------------|---------|
| P0-GAP-1（學習閉環） | 涵蓋（1.6） | 採用報告的決策路徑注入方式 |
| P0-GAP-2（Evolution→Deploy） | 涵蓋（1.7） | 一致 |
| P1-GAP-3（H0 warn-only） | **未涵蓋** | 保持我們的修復計劃（已在 pipeline_bridge 修改為 blocking） |
| P1-GAP-4（交易所條件單） | **未涵蓋** | 保持我們的計劃（Bybit SL/TP 條件單） |
| P1-GAP-5（Scanner→Deployer） | 未直接涵蓋 | 保持我們的計劃 |
| P1-GAP-6（Backtest 生產啟用） | 間接涵蓋（策略 V2 需回測驗證） | 一致方向 |
| P2-GAP-7（L2 門檻過高） | 涵蓋（L1→L2 升級條件精細化） | 採用報告的 6 個量化條件 |

---

## 6. 風險提醒

報告 §11 的最根本風險提醒值得重複：

> **No proven strategy alpha。** 所有策略用標準 TA，無統計邊際驗證。再好的架構，底層無 edge → 淨虧損。

報告建議「Paper 4 週後合併淨 PnL 為負 → 暫停新模組，聚焦 alpha 驗證」。這與我們的 Phase 4（21 天觀察期）方向一致，但報告的觸發條件更務實。

Batch 9A 的確定性適應（ATR 縮放、成本感知）能減少無意義虧損，但不能創造 alpha。真正的 alpha 來源仍是開放問題。

---

*報告完成。核心結論：報告與我們的方向高度一致，零衝突。主要增值在於 (1) 四階段放權框架、(2) 快速通道機制、(3) 策略 V2 升級、(4) 新感知工具（EWMA/Hurst/CUSUM）。建議按上述優先級分批整合。*
