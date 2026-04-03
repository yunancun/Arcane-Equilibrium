# ML/DL 驅動 Agent 自主學習架構 — 設計初稿 v0.4
# ML/DL-Driven Agent Autonomous Learning Architecture — Design Draft v0.4
# 狀態：用戶確認所有決策，待存為正式設計文檔
# 日期：2026-04-03

---

## Context（為什麼做這件事）

### 問題
現有系統的「學習」只是記賬：AnalystAgent 統計勝率 → 微調 Strategist 偏好權重 ±0.1。三個未接線模組（DreamEngine / CognitiveModulator / EvolutionAutoScheduler）都在優化「如何執行」（SL/TP），而非「如何決策」（V2 策略信號參數）。AI（Ollama/Claude）產出分析報告但無下游效果。

### 目標
建立真正的學習閉環：數據採集 → 因果歸因 → ML 驅動的參數優化 → 沙箱驗證 → 閉環執行。Claude 作為「老師」指導本地 ML「學生」，而非直接做交易決策。

---

## 一、架構總覽

```
        ┌─────────────┐
        │  新聞 Agent  │ （未來建設，預留接口）
        └──────┬──────┘
               │ NewsSignal（事件標記，非因果推斷）
     ┌─────────┼────────────────┐
     ▼         ▼                ▼
  Guardian   Regime          Learning System
  (即時)    Detector         (歸因標籤)
     │         │                │
     │         ▼                ▼
     │   Signal Quality     Bayesian Param
     │   Scorer (LightGBM)  Optimizer (Optuna)
     │        │                  │
     │   ┌────┘                  │
     │   │  Partial Pooling      │
     │   │  (James-Stein)        │
     │   ▼                       ▼
     └─► Guardian 審批 ◄─────────┘
              │
         策略執行 + 數據採集
              │
         分佈漂移監控（PSI + Adversarial Validation）
         自適應黑天鵝檢測（4 信號投票）
              │
              ▼
         Claude 老師（週度 Learning Directive）
```

---

## 二、EV_net 目標函數（QC 修正版）

### 原公式問題
v0.2 公式遺漏滑點和 funding rate，會系統性高估 EV。

### 修正公式
```
EV_net = p × (avg_win - c_win) - (1-p) × (avg_loss + c_loss)

c_win  = fee_round_trip + slippage_round_trip + funding_cost(avg_hold_win)
c_loss = fee_round_trip + slippage_round_trip + funding_cost(avg_hold_loss)

funding_cost(t) = position_value × avg_funding_rate × ceil(t / 8h)
slippage = 按 cost_gate.py 的 SLIPPAGE_TIERS 查表（BTC 1bps → Meme 30bps）
```

### 各策略差異化指標（不變）
| 策略 | 主指標 | 約束 |
|------|--------|------|
| MA Crossover（趨勢） | Profit Factor + Payoff Ratio | PF>1.5, PR>2.0 |
| BB Reversion（回歸） | Calmar + MAE 分布 | Calmar>1.0 |
| Funding Arb（套利） | 費後淨收益率 | 顯著覆蓋費用+滑點+basis |
| Grid Trading（網格） | Grid_Efficiency | Inventory_Risk_Ratio < 按幣分級 |
| BB Breakout（突破） | EV_net + Max DD | EV>0, DD<限制 |

### Grid Inventory_Risk_Ratio 按幣種分級（QC 建議）
- 大盤（BTC/ETH）：< 2.0（可承受更大偏移）
- 主流山寨：< 1.5
- Meme 幣：< 1.0（波動極大，必須更保守）

---

## 三、組件設計

### A. Signal Quality Scorer

**模型：** LightGBM 回歸（非二元分類）
- QC 指出二元「是否盈利」丟失收益大小信息
- 改為：`y = net_pnl / ATR`（ATR 標準化淨收益，連續值）
- 輔助：TabPFN（MIT 建議）作為零調參基線，並行運行用於校準參考

**特徵向量（信號觸發時刻快照）：**
```
14 技術指標（ADX, RSI, BB width, KAMA slope, Hurst, OBV...）
regime 狀態（MarketRegimeTracker 的 9 枚舉）
成交量比率（vs 20 日均量）
波動率 regime（EWMAVolEstimator）
時段（亞洲/歐洲/美國盤）
最近 N 筆同策略勝率（用 t-1 及之前數據，防標籤洩漏）
news_severity（近 24h 最高，未來新聞 Agent 接入）
hours_since_last_major_news
```

**校準（MIT 建議）：** Platt scaling 後處理，確保輸出概率可信。GBT 原始輸出校準差，如果用於 Kelly sizing 或置信度門控，未校準的概率會導致倉位計算錯誤。

**Scorer 多樣性（MIT 建議）：** 維持 2-3 個 Scorer 變體（不同特徵子集、不同訓練窗口），用集成 + 分歧度作為信心指標。分歧度高 → 降低倉位。防止跨幣相關性失敗。

**可復用基礎設施：**
- `IndicatorEngine._indicator_cache`：14 指標已有
- `MarketRegimeTracker`：regime 枚舉已有
- `Signal.metadata`：可無縫攜帶 ML 評分
- `TradeAttribution.attribute_trade()`：6 因子歸因可生成標籤

**新建：** FeatureCollector（~200 行）+ 訓練管線 + 推理注入到 PipelineBridge

---

### B. Bayesian Parameter Optimizer

**方法：** Optuna TPE 替代 EvolutionEngine grid search
- TPE 在 5-8 維參數空間高效（20-50 次評估即可找到合理最優）
- 搜索 V2 策略參數（adx_threshold, rsi_threshold 等），非 SL/TP

**探索機制（MIT 核心建議）：**
- 現有設計純 exploitation（觀察結果 → 調向最優）
- 加入 Thompson Sampling：從參數後驗分佈中採樣，而非總是取最優
- 自動平衡 explore vs exploit，有理論 regret bound

**Walk-forward 驗證（MIT + QC 聯合建議）：**
- 單次 70/30 不夠 → 改為 6-fold Combinatorial Purged CV (CPCV)
- 加入 embargo period（至少等於最大交易持倉時間）
- Multiple testing correction：Benjamini-Hochberg FDR（25 幣 × 5 策略 × 3 regime = 375 假設檢驗）

**信任域約束（MIT 建議，替代固定 20%）：**
- 步長 ∝ 1 / posterior_variance
- 不確定時小步，確定時可大步
- 比固定 20% 更有理論基礎

**阻塞前置（FA 確認）：** `StrategyBase.update_params()` 不存在，5 個策略全需改造。這是整個方案最硬的結構性障礙。

---

### C. 跨幣遷移學習

**簡化為 2 層（QC + MIT 共識）：**
```
原方案：Global → Group(3) → Symbol  ← 3 Group 無法收斂
修正版：Global → Symbol              ← Group 信息作為 covariate 而非層級
```

**用 James-Stein 部分池化替代完整分層貝葉斯（MIT 建議）：**
- 每幣參數 = weighted_avg(該幣 MLE, 全局均值)
- 權重由樣本量決定（數據多 → 信任個體，數據少 → 拉向全局）
- 80% 效果，10% 實現成本
- 不需要 MCMC/Stan，一個下午能實現

**從數據學分組（MIT 建議）：**
- 不硬編碼大盤/山寨/Meme
- 用 k-means 在 rolling 特徵向量（波動率、BTC 相關性、均值回歸係數、成交量 profile）上聚類
- 分組結果作為 James-Stein 的 covariate

**正規化（QC 修正）：**
- 主標準化：PnL / entry_notional（穩健，不依賴 ATR）
- 風險調整時才用 ATR
- 新幣（< 30 天數據）用 Group 中位特徵作為 prior

---

### D. 自適應黑天鵝檢測

**4 信號投票（保留，但修正參數）：**

| 檢測器 | 原參數 | QC 修正 |
|--------|--------|---------|
| 統計偏離 | 3σ (MAD×1.4826) | **6×MAD**（肥尾下等效 3σ，不乘錯誤的 1.4826 換算因子） |
| 全市場相關性 | > 0.9 | > 0.85（保守方向） |
| 成交量異常 | > 5× 均量 | 保持（合理） |
| 速度異常 | 15min > 正常日跌幅 | 保持（合理） |

**投票規則保持：** 2/4 觀察模式 / 3/4 升級風控 / 4/4 全面防禦

**時間衰減修正（QC 建議）：**
```
正常期：λ = 0.025（半衰期 ~28 天，而非 70 天）
黑天鵝後：λ = 0.05（半衰期 ~14 天，保持）
關鍵區分：
  - 黑天鵝事件本身 → λ=0（永久標記，永不衰減——教訓要記住）
  - 黑天鵝前的正常期數據 → λ=0.05（加速遺忘——市場結構已變）
  - 切換用 sigmoid 平滑，而非階梯跳變
```

---

### E. 分佈漂移檢測

**PSI 保留但校準閾值（QC + MIT 共識）：**
- 不用銀行業 0.1/0.25
- 用歷史 6-12 個月的相鄰窗口 PSI 經驗分佈校準
- 粗估幣圈合理閾值：~0.2（穩定）/ 0.5（暫停）
- 按幣種分級（BTC 閾值低、Meme 閾值高）

**補充檢測器（MIT 建議）：**
- **Adversarial Validation**（週度）：用 LightGBM 區分「近期數據」vs「歷史數據」，AUC > 0.6 → 標記漂移。復用已有的 LightGBM 基礎設施。
- **ADWIN**（即時）：在 Scorer 的 rolling accuracy 上運行，提供比 PSI 更即時的漂移檢測。
- **Scorer 性能監控**：tracking rolling Brier score / AUC。模型本身的性能衰退 ≠ 輸入特徵漂移，兩者都要監控。

---

### F. 新聞 Agent 整合

**降級為事件標記（QC + MIT 共識）：**
- 放棄「自然實驗」因果推斷框架（外生性、排他性、SUTVA 全部違反）
- 改為 event-conditioned performance segmentation
- 新聞事件作為 Signal Quality Scorer 的額外特徵，而非獨立的因果推斷工具

**三層接入保留：**
- Guardian（即時風控）：severity ≥ 0.8
- Regime Detector（環境判斷）：severity 0.5-0.8
- Learning System（歸因標籤）：所有事件

---

### G. Claude-as-Teacher

**Learning Directive 結構化輸出（非報告）：**
```json
{
  "focus_strategy": "bb_reversion",
  "focus_regime": "ranging→trending transition",
  "hypothesis": "BB Reversion 在 regime 轉換前 2 根 K 線虧損率上升...",
  "suggested_experiment": {
    "type": "shadow_branch",
    "param_change": {"regime_sensitivity": "+1 bar lookahead"},
    "evaluation_metric": "win_rate in transition trades"
  },
  "ml_review": {
    "scorer_calibration": "predicted 70% but actual 52%, recalibrate",
    "feature_importance_concern": "over-reliance on RSI in trend regime",
    "exploration_suggestion": "try ADX 18-22 range, current posterior too narrow"
  },
  "review_in": "50 new trades or 7 days"
}
```

**成本估算：** ~$8-16/月（與現狀持平，但 ROI 顯著提升）

---

## 四、樣本量與防過擬合（QC 修正版）

### 樣本量：誠實定義為「可操作性妥協」

| 策略 | 統計理想 n | 可操作妥協 n | CI 寬度 | 對策 |
|------|-----------|-------------|---------|------|
| 趨勢 | 370 | 150 | ~16% | CI 寬度 → 約束調整幅度（CI 越寬，調整越小） |
| 回歸 | 350 | 120 | ~17% | 同上 |
| 套利 | 196 | 80 | ~16% | 同上 |

**核心改進：** 調整幅度不再固定 20%，而是 `max_adjustment = min(20%, 10% / CI_width)`。樣本越少 → CI 越寬 → 允許調整越小。

### 防過擬合三道防線

1. **CPCV**（6-fold，帶 embargo）替代單次 70/30
2. **Benjamini-Hochberg FDR** 多重檢驗校正
3. **Deflated Sharpe Ratio** 考慮策略選擇偏差
4. **Power analysis** 替代固定 50 筆 cooldown → 計算所需樣本量以 80% power 檢測 5% EV 改善

---

## 五、技術可行性與實施路線（FA 評估）

### 阻塞項
1. **StrategyBase.update_params()** — 不存在，5 策略全需改造（B 的硬前置）
2. **FeatureCollector** — 信號觸發時不保存指標快照（A/E/F 共同前置）

### 依賴安全性
| 依賴 | macOS ARM | Linux | 風險 |
|------|-----------|-------|------|
| scikit-learn | ✓ wheel | ✓ | 安全 |
| lightgbm | ✓ (v4.0+) | ✓ | 基本安全，可降級 sklearn |
| optuna | ✓ 純 Python | ✓ | 完全安全 |

### 五階段實施路線

```
Phase 1 (基礎設施，2-3 週):
  ├── E. PSI 漂移檢測（最簡單，零重構，驗證 ML 部署流程）
  └── A.1 FeatureCollector（所有 ML 組件的共同前置）
  
Phase 2 (核心 ML，3-4 週):
  ├── A. Signal Quality Scorer + Platt 校準
  └── D. 黑天鵝檢測（獨立，可與 A 並行）

Phase 3 (參數優化，2-3 週):
  ├── B.0 StrategyBase.update_params() 改造（硬前置）
  └── B. Bayesian Optimizer + Thompson Sampling

Phase 4 (整合層，2-3 週):
  ├── F. 新聞 Agent 接口（預留）
  └── G. Claude-as-Teacher（依賴 A+B 就位）

Phase 5 (研究性質，3-4 週):
  └── C. James-Stein 跨幣部分池化（依賴充足交易數據）

總計：~12-17 週
```

### Rust 遷移衝突處理
- ML 模組明確標記為 Python-only，不進入 Rust 遷移
- Rust 引擎通過 PyO3 FFI 消費 ML 評分結果
- 與 R-07 灰度不衝突（ML 是獨立管線）

### Principle 7 邊界（強制）
- ML 推理結果只能是 advisory（調整 Signal.confidence）
- 參數變更必須經 ExperimentLedger → TruthSourceRegistry → Guardian 審批
- ML 永遠不能直接覆蓋風控閾值（P0/P1 硬邊界代碼鎖定）

---

## 六、三方審查總結

| 維度 | QC 評分 | MIT 評分 | 主要改進 |
|------|---------|---------|---------|
| 目標函數 | 2.5→4.0 | — | 加入 slippage + funding |
| 標籤定義 | 2.0→4.0 | — | 二元→回歸（net_pnl/ATR） |
| 跨幣遷移 | 2.0→3.5 | — | 3 層→2 層 + James-Stein |
| 漂移檢測 | 1.5→3.5 | — | PSI 校準 + Adversarial Validation |
| 防過擬合 | — | 改善 | CPCV + embargo + FDR + power analysis |
| 探索機制 | — | 新增 | Thompson Sampling（最大單項改進） |
| 模型校準 | — | 新增 | Platt scaling |
| 新聞整合 | 1.5→3.0 | — | 降級為事件標記 |
| 技術可行性 | — | 7.5/10 | 依賴安全，主阻塞是 update_params() |

---

## 七、已確認決策（v0.4 全部納入主線）

### 7.1 TabPFN — 納入 Phase 2 作為校準基線
- 與 LightGBM 並行運行，提供獨立的過擬合檢測信號
- 零調參，實現成本低

### 7.2 Contextual Bandits (LinUCB + Thompson Sampling) — 納入 Phase 3 主線
- 統一 Scorer + Optimizer 的探索-利用框架
- **對收益直接有效** — 解決純 exploitation 卡在局部最優的根本問題
- Thompson Sampling 在 Bayesian Optimizer 的參數後驗上採樣

### 7.3 Grid Trading 多目標 Bayesian 優化 — 納入 Phase 3
- Optuna 多目標（Pareto）：最大化 Grid_Efficiency + 最小化 Inventory_Risk_Ratio
- 可優化參數：grid_spacing_pct / grid_count / range_width
- 關鍵上下文：波動率 regime / ATR-price ratio / funding rate

---

## 八、語言分層決策（已確認）

```
訓練層（Python-only）：
  LightGBM / scikit-learn / Optuna / PyTorch
  → 每週離線訓練，速度非瓶頸
  → ML 生態系統只有 Python 成熟

推理層（Rust，與現有密集計算層一致）：
  openclaw_engine 的 tick_pipeline.rs / intent_processor.rs / strategies/
  → ML 模型導出 ONNX → Rust `ort` crate 加載推理
  → 推理 ~0.01ms，完全在 tick 處理 SLA 內
  → 與現有 Rust 密集交易管線一致（不引入 Python 推理延遲）

橋接層（PyO3 FFI）：
  openclaw_pyo3 已存在
  → Python 訓練 → ONNX 導出 → Rust 加載
  → 模型更新時 Python 寫 ONNX → Rust 熱加載
```

---

## 九、DL 應用場景（已確認，僅限三個）

### 原則：交易數據稀缺 → GBT。K 線數據充裕 → DL。

### DL-1：Symbol Embedding（幣種嵌入）— Phase 5
```
Autoencoder 在 K 線 + 成交量特徵上訓練
  輸入：某幣最近 30 天日度特徵序列
  輸出：8 維嵌入向量
  作用：替代硬編碼分組，作為 James-Stein 的 covariate
  數據：K 線（充裕），不用交易數據
```

### DL-2：Regime Detection 增強 — Phase 4（Shadow 運行）
```
LSTM / Temporal Transformer 在 K 線序列上
  輸入：最近 50 根 K 線 OHLCV + 指標
  輸出：regime 概率分佈 {trending: 0.7, ranging: 0.2, volatile: 0.1}
  優勢：概率輸出 + 提前 1-2 K 線預警 regime 轉換
  部署：先 Shadow 運行與規則式 detector 對比，驗證後替代
```

### DL-3：時序基礎模型 — Phase 2（零訓練成本）
```
Google TimesFM / Amazon Chronos / Lag-Llama
  零訓練 — 直接 zero-shot 推理
  不預測價格，生成「市場狀態特徵」：
    - 預測殘差 = 市場偏離正常軌跡程度
    - 預測不確定性 = 市場可預測性
  作為 Signal Quality Scorer 的額外特徵
```

---

## 十、更新後的完整實施路線

```
Phase 1 (基礎設施，2-3 週):
  ├── E. PSI 漂移檢測（零重構，驗證 ML 部署流程）
  ├── A.1 FeatureCollector（所有 ML 組件共同前置）
  └── DL-3 時序基礎模型特徵（零訓練，早期即可啟動）

Phase 2 (核心 ML，3-4 週):
  ├── A. Signal Quality Scorer (LightGBM) + Platt 校準 + TabPFN 基線
  ├── A.onnx ONNX 導出 + Rust ort 推理整合
  └── D. 黑天鵝檢測（獨立，與 A 並行）

Phase 3 (參數優化 + 探索，3-4 週):
  ├── B.0 StrategyBase.update_params() 改造（5 策略）
  ├── B. Bayesian Optimizer (Optuna TPE) + Thompson Sampling
  ├── B.grid Grid Trading 多目標 Pareto 優化
  └── B.cb Contextual Bandits (LinUCB) 統一框架

Phase 4 (整合層 + DL，2-3 週):
  ├── F. 新聞 Agent 接口（事件標記，非因果推斷）
  ├── G. Claude-as-Teacher（Learning Directive 結構化輸出）
  └── DL-2 Regime Detection LSTM（Shadow 運行，與規則式對比）

Phase 5 (跨幣遷移 + DL，3-4 週):
  ├── C. James-Stein 跨幣部分池化
  └── DL-1 Symbol Embedding（Autoencoder，替代硬編碼分組）

總計：~13-18 週
```

---

## 十一、三方審查總結（更新版）

| 維度 | QC 評分 | MIT 評分 | v0.4 狀態 |
|------|---------|---------|----------|
| 目標函數 | 2.5→4.0 | — | ✅ 加入 slippage + funding |
| 標籤定義 | 2.0→4.0 | — | ✅ 二元→回歸（net_pnl/ATR） |
| 跨幣遷移 | 2.0→3.5 | — | ✅ James-Stein + DL-1 嵌入 |
| 漂移檢測 | 1.5→3.5 | — | ✅ PSI 校準 + Adversarial |
| 防過擬合 | — | 改善 | ✅ CPCV + embargo + FDR |
| 探索機制 | — | 新增 | ✅ Thompson Sampling + LinUCB |
| 模型校準 | — | 新增 | ✅ Platt scaling + TabPFN 基線 |
| 新聞整合 | 1.5→3.0 | — | ✅ 降級為事件標記 |
| 語言分層 | — | — | ✅ 訓練 Python / 推理 Rust ONNX |
| DL 應用 | — | — | ✅ 3 場景（嵌入/Regime/基礎模型） |

---

*v0.4 · 2026-04-03 · 所有決策已確認 · QC + MIT DL/ML + FA 三方審查*
*下一步：存為正式設計文檔 → 納入 TODO.md → Phase 1 開始執行*
