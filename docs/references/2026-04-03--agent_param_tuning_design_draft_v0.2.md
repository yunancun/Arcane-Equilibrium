# Agent 自主調參設計草稿 v0.1
# Agent Autonomous Parameter Tuning — Design Draft v0.1
# 狀態：草稿（Discussion Draft）· 未納入 TODO · 需繼續深入討論
# 日期：2026-04-03

---

## 背景與動機

### 發現的架構問題（2026-04-03）

當前系統中，Strategist Agent 與 5 個策略模型（MA Crossover / BB Reversion / BB Breakout / FundingRate Arb / Grid Trading）完全平行運行、互不干涉：

- 策略靠 `SignalEngine → StrategyOrchestrator → strategy.on_signal()` 自動驅動，Agent 從不調用策略
- 所有 V2 參數（`adx_threshold / use_kama / rsi_threshold / regime_aware / ou_dynamic` 等）在構造後不可變
- Create API 只傳 `qty_per_trade`，其他 V2 參數全靠硬編碼默認值
- Agent 的學習輸出只影響推薦置信度權重，不影響任何策略行為

### 目標願景

讓 Agent 能夠憑藉「經驗」（歷史交易數據、信號攔截統計、市場狀態觀察）自主判斷並調整策略的 V2 參數——目標不是「下更多的單」，而是從**收益和風險角度**出發，提升策略的整體質量。

---

## 核心認知：目標函數設計

### 為什麼「更多交易」是錯誤目標

交易量本身沒有任何 α 來源。策略的盈利能力來自信號的期望值（EV），而不是信號的頻率。放寬參數提升交易數量等價於以下三種情況之一：

1. 原本的過濾條件確實過於嚴格，排除了部分正 EV 信號（需要驗證）
2. 過濾條件被放寬到讓負 EV 信號通過（系統性毀滅）
3. 在高噪聲 regime 下強行下單（費用侵蝕 EV 變成負值）

現有 V2 過濾器設計哲學（ADX 過濾、regime 感知、multi-TF 確認）本質上是**信號質量篩選器**，犧牲頻率換 EV 提升。以「更多交易」為目標等於反向優化這些篩選器。

### 正確的目標函數：分層多指標體系

**核心主指標（最大化目標）：**

```
EV_net_per_trade = win_rate × (avg_win - fee_avg)
                 - (1 - win_rate) × (|avg_loss| + fee_avg)
```

任何參數調整讓 `EV_net` 下降，即為錯誤調整，無論交易數量增加多少。

**輔助指標（健康度參考）：**

```
Profit_Factor   = Σ(winning_pnl) / Σ(|losing_pnl|)  → 目標 > 1.5
Payoff_Ratio    = avg_win / avg_loss                  → 趨勢策略目標 > 2.0
Fee_Drag_Rate   = total_fees / Σ(|gross_pnl|)         → 警戒線 > 30%
```

**風控約束指標（不可惡化）：**

```
Calmar_Ratio    = Annualized_Return / Max_Drawdown     → 不能因調參下降
Max_Drawdown_pct = 基於累計 PnL 序列的最大回撤         → 硬上限
```

**Kelly Fraction（診斷用，非優化目標）：**

```
Kelly_f = win_rate - (1 - win_rate) / (avg_win / avg_loss)
```

Kelly_f < 0 → 策略在數學上無優勢，調參無意義，先診斷 EV 為負的根因。

---

## 各策略類型的差異化目標

| 策略 | 天然特徵 | 主指標 | 目標值 | 核心風險 |
|------|---------|--------|--------|---------|
| **MA Crossover**（趨勢） | 低勝率 30-45%，靠大盈小虧 | Profit Factor + Payoff Ratio | PF>1.5, PR>2.0 | 震蕩市場產生大量小虧 |
| **BB Reversion**（回歸） | 高勝率 60-75%，尾部風險大 | Calmar + MAE 分布 | Calmar>1.0 | 趨勢行情單次巨虧吞掉積累 |
| **Funding Arb**（套利） | 低風險低收益高確定性 | 費後淨收益率（絕對值） | 顯著覆蓋費用+滑點 | basis 風險 + 持倉超時 |
| **Grid Trading**（網格） | 震蕩收割，趨勢受損 | Grid Efficiency + 資金利用率 | regime 感知下的效率 | 趨勢行情單邊積累存貨 |
| **BB Breakout**（突破） | 中等勝率，依賴量能確認 | EV_net + Max Drawdown | EV>0, DD<限制 | 假突破頻繁觸發 |

> **注意**：Grid Trading 不適合用 Sharpe/Calmar 評估，需要獨立的效率指標體系。

---

## 兩個致命數據缺口（必須先補）

在以下兩個基礎設施補齊之前，任何調參都是**盲目的**：

### 缺口 1：交易觸發時的參數快照

現有 `record_trade_result()` 記錄了交易結果，但沒有記錄觸發該交易時策略的參數狀態（`adx_threshold` 當時是多少？`confidence` 多少？regime 是什麼？）。

沒有這個快照，就無法做「參數配置 → 交易結果」的因果歸因。

**需要補充的字段**（每筆交易記錄）：
```
param_snapshot: {
    adx_threshold, use_kama, multi_tf_confirm,  # MA Crossover
    rsi_threshold, regime_aware,                 # BB Reversion
    volume_ratio_threshold, donchian_confirm,    # BB Breakout
    funding_threshold, delta_neutral,            # Funding Arb
    ou_dynamic, grid_count,                      # Grid
    current_regime,                              # 通用
    min_confidence, cooldown_ms,                 # 通用
}
```

### 缺口 2：信號攔截記錄

現在只記錄「成交的交易」，沒有記錄「被過濾掉的信號」：

- 被 `adx_threshold` 攔截的有多少？
- 被 `regime_aware` 攔截的有多少？
- 被 `min_confidence` 攔截的有多少？

沒有攔截記錄，無法計算 `Signal_Filter_Efficiency`，無法判斷是過度過濾還是欠過濾。

**需要的新統計結構**（每個策略）：
```
filter_block_stats: {
    adx_filter: {blocked: N, passed: M},
    confidence_filter: {blocked: N, passed: M},
    regime_filter: {blocked: N, passed: M},
    volume_filter: {blocked: N, passed: M},     # BB Breakout
    donchian_filter: {blocked: N, passed: M},   # BB Breakout
    cooldown_filter: {blocked: N, passed: M},
}
```

---

## 策略健康卡：六個核心數字

每個策略、每個 regime 分組，定期輸出以下六個數字：

```
1. EV_net_per_trade        最核心，正值才有意義

2. Profit_Factor           Σ winning_pnl / Σ |losing_pnl|
                           > 1.5 合格，> 2.0 優秀

3. Payoff_Ratio            avg_win / avg_loss
                           趨勢策略目標 > 2.0

4. Fee_Drag_Rate           total_fees / Σ |gross_pnl|
                           > 30% 說明費用過高

5. Max_Drawdown_pct        基於累計 PnL 序列
                           不能超過設計上限

6. Signal_Filter_Efficiency = 成交信號數 / (成交 + 攔截) × EV_of_taken_trades
                           需要缺口 2 數據才能計算
                           高攔截率 + 高 EV → 過濾器工作正常
                           高攔截率 + 低 EV → 過濾器可能過嚴
                           低攔截率 + 低 EV → 過濾器明顯失效
```

---

## 調參決策規則（初稿）

```
IF EV_net < 0 AND sample_n >= min_threshold:
    → 不調參，先診斷根因
    → 考慮暫停策略，上報 Guardian

IF EV_net > 0 AND PF > 1.5 AND Max_DD < 上限:
    → 策略健康，不需要調參（不要為了調而調）
    → 頂多小幅收緊過濾條件

IF EV_net > 0 BUT PF < 1.2:
    → 虧損交易過多 → 考慮收緊過濾條件（提高閾值）
    → 驗證：收緊後 Signal_Filter_Efficiency 是否提升

IF Fee_Drag_Rate > 30%:
    → 費用問題，非參數問題
    → 延長 cooldown 降頻，或評估 limit order 替代 market order

IF Signal_Filter_Efficiency 顯示高攔截率 AND 被攔截信號 EV 也高:
    → 可能過濾器過嚴，考慮小幅放寬
    → 必須先有攔截記錄數據
```

---

## 防過擬合機制

### 最低樣本量門檻（硬性要求，代碼鎖定）

基於二項分布 95% 置信區間寬度 < 10% 的統計要求：

| 策略類型 | 最低樣本量 | 原因 |
|---------|----------|------|
| 趨勢策略（MA/Breakout） | **150 筆** | 低勝率需要更多樣本才能穩定 |
| 均值回歸（BB Reversion） | **120 筆** | 高勝率但尾部事件重要 |
| 套利策略（Funding Arb） | **80 筆** | 確定性高，樣本需求低 |
| 網格策略（Grid） | 待定，需另設效率指標 | 不以筆數為主要評估單位 |

**低於門檻 → 絕對禁止調參。**

### Regime 標籤隔離

- 每筆交易必須帶 regime 標籤（trending / ranging / volatile）
- 評估 EV 時按 regime 分組
- 每個 regime 分組的樣本量**獨立達到最低門檻**，才能對該 regime 下的參數做調整
- trending 的數據不能驅動 ranging 下的參數調整

### 調整幅度保守性約束

- 單次調整幅度 ≤ 當前值的 **20%**
  - ADX 20 → 最多調到 16 或 24
  - 不允許一步從 20 跳到 10 或 30
- 連續調整冷卻期：調整後至少新增 **50 筆交易**才能再次評估

### Walk-forward 思路（簡化版）

- 不使用全量歷史數據
- 按時間順序：前 70% 計算指標，後 30% 驗證方向一致性
- 兩段方向不一致 → 不允許調參

---

## 哪些參數永遠不能自動調整

| 參數類型 | 舉例 | 原因 |
|---------|------|------|
| 架構級開關 | `use_kama`, `multi_tf_confirm`, `donchian_confirm` | 改變策略性質，不是調整程度 |
| 風控 P0/P1 邊界 | 所有止損閾值，`max_drawdown` 上限 | Guardian 職責，Strategist 無權觸碰 |
| 持倉中的危險參數 | FundingArb 的 `delta_neutral` | 持倉中改變等於單腿裸露 |
| 系統性風控 | `execution_authority`, `max_retries` | 硬邊界（原則 §四） |

---

## 調參的授權矩陣（初稿）

| 調整類型 | 示例 | Phase 2 | Phase 3+ |
|---------|------|---------|---------|
| 收緊過濾（提高門檻） | ADX 20→22 | 沙箱實驗 + Operator 確認 | Guardian 可自動審批 |
| 小幅放寬（≤10%） | ADX 20→18 | Operator 確認 | Guardian 審批 |
| 大幅放寬（10-20%） | ADX 20→16 | Operator 確認 + 書面理由 | Operator 確認 |
| 超出 20% 調整 | ADX 20→12 | **禁止** | **禁止** |
| 架構級開關 | `use_kama` 切換 | **禁止** | **禁止** |

---

## 架構設計思路（初稿）

### 三層結構

```
數據層：StrategyPerformanceStore
  ↓ 補充：param_snapshot + filter_block_stats
評估層：StrategyEvaluator（策略健康卡，定期計算）
  ↓ 按 regime 分組，統計六個核心指標
提議層：ParamAdjustProposal → Guardian 審批 → Paper 沙箱 → Operator 確認
```

### 沙箱實驗機制

Phase 2 內，所有調參先在「影子策略實例」（`MA_Crossover_exp_001`）上跑，不動主策略實例（`MA_Crossover_BTCUSDT`）。`StrategyOrchestrator` 已支持多實例，可直接複用。

### 可調參數聲明（每個策略加 TUNABLE_PARAMS）

```python
# 示意，非最終代碼
TUNABLE_PARAMS = {
    "adx_threshold":  {"min": 10.0, "max": 35.0, "step": 2.5, "hot_changeable": True},
    "min_confidence": {"min": 0.2,  "max": 0.6,  "step": 0.05, "hot_changeable": True},
    "cooldown_ms":    {"min": 60_000, "max": 900_000, "step": 60_000, "hot_changeable": True},
    # use_kama / multi_tf_confirm 不在列表 → 不允許自動調整
}
```

### 評估週期

```
實時：EV_net rolling window（最近 30 筆）監控
日度：全量六指標 + regime 分組分析
週度：是否產生 ParamAdjustProposal（需 ≥ 最低樣本量）
月度：Operator 手動審查調參歷史
```

---

## 實施路徑（初稿，未納入 TODO）

**Step 0（基礎，先做）：補兩個數據缺口**
- 每筆交易加 `param_snapshot` 字段
- 每個策略加 `filter_block_stats` 計數器

**Step 1：策略健康卡輸出**
- `StrategyEvaluator` 計算六個核心指標
- 按 regime 分組統計
- 暴露到 GUI（策略詳情頁）

**Step 2：Strategist 輸出 ParamAdjustProposal**
- 定期任務（非 tick 驅動，每 24 小時或 50 筆新交易後）
- 讀健康卡 + 調參決策規則 → 生成提議
- 通過 Guardian 審批流

**Step 3：沙箱實驗 + Operator 確認**
- 影子實例並行跑
- Operator GUI 審閱比較結果後確認或拒絕

**Step 4（Phase 3 後）：Guardian 自動審批**
- 四階段放權框架的一部分

---

## 開放問題（v0.2 已解決）

### Q1：Grid Trading 效率指標 ✅

Grid 不適用傳統 win_rate/Sharpe/Calmar，因為沒有明確「一筆交易」概念，敵人是趨勢行情下的庫存積累。

**指標體系：**
```
主指標：
  Grid_Efficiency = Σ(完成往返 × 每次利潤) / (分配資本 × 部署時間)
  → 單位時間、單位資本的網格利潤率

風控約束：
  Inventory_Risk_Ratio = |淨庫存市值| / Σ(已實現網格利潤)
  → >1.0 = 庫存虧損超過利潤，策略水下
  → 硬上限 1.5，超過即暫停

輔助：
  Range_Utilization = 被觸及格子數 / 總格子數
  Breakeven_Range = 偏移多少%後庫存虧損 > 網格利潤
```

Grid 調參目標：在 `Inventory_Risk_Ratio < 1.5` 前提下最大化 `Grid_Efficiency`。

### Q2：被攔截信號 EV 估算 ✅

**結論：放棄精確 EV 估算，改用 Signal_Correctness_Rate 對比法。**

反事實 EV 估算本質上不可靠（需模擬完整交易生命週期）。改為：
```
Signal_Correctness_Rate = (方向正確的被攔截信號數) / (總被攔截信號數)
「方向正確」= 價格在信號後 N 小時內朝信號方向移動 > X%
```

比較已通過 vs 被攔截信號的 correctness：
- 被攔截 correctness ≈ 已通過 → 過濾器可能過嚴
- 被攔截 correctness ≪ 已通過 → 過濾器工作正常

OpportunityTracker 框架可復用，但需改為自動觸發（not 手動 record_skipped）。

### Q3：多策略組合 vs 單策略調參 ✅

**結論：作為 Guardian 審批 ParamAdjustProposal 時的附加約束，不需獨立系統。**

```
拒絕調參 if:
  1. 策略間 PnL 相關性增加 > 0.1
  2. 組合 Max Drawdown 增加 > 10%
  3. 單一策略貢獻 > 60% PnL
```

Guardian 本就負責組合級風險（原則 #16），調參審批是職責延伸。

### Q4：早期樣本稀疏期策略 ✅

150 筆趨勢策略在 Paper 可能需 2-3 月。按價值排序的有意義活動：

1. **立即開始數據採集**（最重要）— 每筆缺 param_snapshot + filter_block_stats 的交易 = 浪費的學習機會
2. **回測預校準** — 用歷史 K 線排除明顯不合理的參數區間（非找最優）
3. **信號質量觀察** — 持續輸出健康卡觀察值，標記異常趨勢
4. **跨 symbol 池化**（有條件）— 同策略不同 symbol 可合併，需按 ATR 標準化 + regime 對齊
5. **影子分支實驗** — 多實例不同參數並行跑，加速比較數據積累

### Q5：學習速度設計 ✅

**核心：學習速度自適應，不固定。**

```
觸發條件（三者同時滿足）：
  1. 該策略新增 ≥ 50 筆交易（since 上次評估）
  2. 當前 regime 下新增 ≥ 30 筆（regime 隔離）
  3. 距離上次調參 ≥ 7 天（冷卻期）

速度自適應：
  穩定 regime → 低 EMA α（0.2）→ 信任歷史更多
  Regime 轉換期 → 高 EMA α（0.5）→ 更快適應
  高波動期 → 加寬置信區間（要更多數據）

防護：
  - 單次調整 ≤ 20%
  - 連續同方向調整 ≤ 3 次（防 drift）
  - 每次調整記錄 before/after snapshot + 理由
```

---

## 現有模組評估（v0.2 新增）

### 三個未接線模組 vs EV_net 框架

| 模組 | 對齊度 | 核心問題 | 結論 |
|------|--------|---------|------|
| DreamEngine | 低（20%） | 只搜索 SL/TP，隨機方向入場不測策略 alpha，無 regime 感知 | 概念保留，搜索空間+模擬模型需重新設計 |
| CognitiveModulator | 中（40%） | 調 Strategist 元參數非策略 V2 參數，規則是「虧了就保守」非數據驅動 | 保留作 risk-dampener，非學習引擎 |
| EvolutionEngine | 中（50%） | 只用 Sharpe，參數是 SL/TP 非 V2，無 regime 分組，無 walk-forward | 骨架可復用，三核心維度需重做 |

**共同根因：三者都在 AGT-1 問題識別前設計，優化「如何執行」而非「如何決策」。**

### 現有學習現狀診斷

- 唯一閉環：Trade → AnalystAgent → TSR → Strategist preference weights ±0.1（記賬式學習）
- AI 角色：情報分析師 + 事後學習員，非決策主幹
- 缺失：因果歸因 / 閉環執行 / 主動探索
- 評估：75% 設計 / 40% 實現 / 5% 真正接通

---

*草稿版本 v0.2 · 2026-04-03 · v0.1 五個開放問題已解決 + 模組評估*
*下一步：基於 v0.2 方向設計完整學習閉環架構 → 實施規劃*
