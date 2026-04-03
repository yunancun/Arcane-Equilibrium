# QC 驗證報告：外部改善報告數學模型 vs Batch 9A 兼容性分析
# QC Validation: External Improvement Report Math Models vs Batch 9A Compatibility

> 審查人：QC（Quantitative Consultant）
> 日期：2026-04-03
> 範圍：外部報告 10 項數學修正 vs 我們已實施的 Batch 9A
> 結論：**6/6 兼容，0 衝突，3 項採用，2 項疊加，1 項暫緩**

---

## 1. Kelly 模型對比

### 報告方案
- 1/8 Kelly（<200 筆）→ 1/6（200-500 筆）→ 1/4（>500 筆）
- 生存偏差修正：將未實現虧損折算為等效虧損交易，調整 win_rate
- 運行時間 < 2x 平均持倉周期 → 退化為 Fixed Fractional

### 我們計劃的 U-14
- Kelly fraction GUI 展示（QC 審查報告 §5.3 S4 建議項）
- 尚未實施，僅為「SHOULD」級建議

### 結論：報告版本更完備，採用報告版本

理由：
1. **分級 Kelly 是正確的**。1/4 Kelly 在小樣本下確實太激進。我昨天的報告算了 f* = -0.014（當前策略不值得交易），但沒有明確給出樣本量分級方案。報告的 200/500 門檻合理。
2. **生存偏差修正是真問題**。快止盈慢止損的策略（正是我們 MA Crossover 的特徵：70% 勝率 + 0.42 R:R）會系統性高估 win_rate。報告的折算公式數學上正確：將 unrealized_loss 等效為 `|unrealized_loss| / |avg_loss|` 筆虧損交易，重新計算 win_rate。
3. **「不足 2x 持倉周期退化為 Fixed Fractional」是好的防護**。冷啟動時 Kelly 的輸入全是噪音。

**一個修正**：報告的 `avg_holding_period > 0 and current_run_time < avg_holding_period * 2` 判定中，`current_run_time` 語義不清。應改為 `total_observation_time`（策略運行總時長），而非單筆交易持有時間。否則每筆新交易開倉時 current_run_time=0，永遠觸發退化。

**與 Batch 9A 的關係**：無衝突。Batch 9A 處理的是成本門檻和 ATR 止損，Kelly 是倉位大小的獨立維度。兩者正交。

---

## 2. 波動率估計：EWMA vs ATR 雙窗口

### 報告方案
- EWMAVolEstimator：lambda 按時間框架調整（1m=0.90, 1h=0.94, 1d=0.97）
- 含 hist_mean 長期均值（衰減 0.995）和 vol_regime 分類（high/normal/low）

### 我們已做的（Batch 9A）
- ATR 快/慢雙窗口：max(ATR_5, ATR_14)

### 結論：互補，不衝突，同時使用

數學上它們測量的是不同東西：
- **ATR** = 價格範圍的非參數估計（含日內高低差），對跳躍敏感
- **EWMA Vol** = 收益率方差的指數加權估計，對連續波動敏感

兩者的用途應該分開：

| 用途 | 用哪個 | 理由 |
|------|--------|------|
| 止損距離計算 | ATR（max(5,14)） | 止損需要覆蓋價格範圍，ATR 直接測量這個 |
| Regime 分類 | EWMA vol_regime | 波動率相對歷史的高低，EWMA 的 ratio 比 ATR 的絕對值更穩定 |
| 入場過濾 | ATR_pct vs 成本門檻 | 已在 Batch 9A 實現 |
| Risk Parity 權重 | EWMA vol | 跨幣種波動率歸一化，EWMA 更平滑 |

**不要用 EWMA 替代 ATR 做止損**。EWMA 是收益率方差（沒有日內範圍信息），在 gap 行情中會嚴重低估所需止損距離。

**報告的 hist_decay 從 0.999 改為 0.995 是正確的**。0.999 的半衰期 ~693 bars，在 1 分鐘框架下就是 11.5 小時，在加密市場日波動 3-5% 的環境下太慢了。0.995 的半衰期 ~138 bars（2.3 小時@1m）更合理。

---

## 3. Regime 檢測：Hurst vs RegimeDetectorRule

### 報告方案
- Hurst Exponent（R/S 分析），min_lag=10, max_lag=100
- 閾值 0.40/0.60（中間為不確定）
- HurstHysteresis：連續 6 個週期才確認切換
- 附錄 C.3 修正：不確定區間凍結計數（不加不減）

### 我們現有的
- MarketRegimeTracker（market_regime.py）：基於技術指標啟發式
- RegimeDetectorRule（signal_generator.py）：ATR/BB/volume 組合判定
- 9 種 regime 枚舉，多時間框架支持

### 結論：疊加，不替換

我們的 RegimeDetectorRule 是多指標啟發式，Hurst 是純統計量。它們捕捉不同信息：

- **Hurst** 回答：「價格序列是趨勢性的、均值回歸的、還是隨機的？」
- **RegimeDetectorRule** 回答：「當前市場狀態是什麼？」（含方向、波動率水平、擠壓等）

正確做法：Hurst 作為 MarketRegimeTracker 的一個 **輸入信號**，不是替代品。

具體整合：
```
regime_from_indicators = RegimeDetectorRule.detect()  # 現有
hurst = compute_hurst_exponent(prices)                # 新增
hurst_regime = hysteresis.update(hurst)               # 新增

# 交叉驗證：
if regime_from_indicators == TRENDING and hurst_regime == "mean_reverting":
    confidence *= 0.5  # 指標與統計量矛盾，降低信心
```

**關於 Hysteresis 的數學評估**：

報告 B.2.1 的滯後機制方向正確。C.3 的「凍結」修正（不確定區間不加不減）比 B.2.1 的「-1 衰減」更好。衰減版本的問題是：在 0.40-0.60 區間波動時，每次都 -1，實際上把之前積累的確認計數清掉了，等效於重置。凍結版本保留了之前的進度。

**一個問題**：報告的 `required_consecutive = 6`（6 個 1h bar = 6 小時）。在 crypto 24/7 市場中，6 小時的確認延遲是否太長？趨勢可能在 2-3 小時就走完了。建議：
- 1h 框架用 required=4（4 小時）
- 4h 框架用 required=3（12 小時）
- 1d 框架用 required=3（3 天）

按時間框架調整，不用統一的 6。

**Hurst 計算本身的數學正確性**：R/S 分析的 OLS 擬合是標準做法。min_lag=10 和 max_lag=100 合理（原始 min_lag=2 確實有小樣本偏差）。`len(prices) < max_lag * 2` 的守衛是正確的（至少需要 200 個 bar）。S 的計算用了總體標準差（除以 n 不是 n-1），這是 R/S 分析的標準做法，正確。

---

## 4. CUSUM 策略衰減

### 報告方案
- StrategyHealthMonitor：CUSUM 雙邊檢測（S_h 和 S_l）
- slack = 0.005，閾值 = 0.1
- 硬性兜底：連續 15 筆虧損自動暫停
- reset_cusum() 允許 Analyst 恢復後重置

### 我們現有的
- 完全沒有策略衰減檢測

### 結論：設計基本足夠，需要兩處修正

**CUSUM 數學正確性**：
- 使用的是標準 Page's CUSUM（1954）。S_h 檢測正偏移（策略突然變好），S_l 檢測負偏移（策略衰減）。公式正確。
- online mean 更新 `s["mean"] += (ret - s["mean"]) / s["n"]` 是 Welford 算法，數值穩定，正確。

**需要修正的地方**：

1. **slack = 0.005 和閾值 = 0.1 缺乏校準依據**。CUSUM 的 slack 和閾值需要根據期望的 ARL（Average Run Length）來設定。slack = 0.5σ 和閾值 = 5σ 是經典選擇（對應 ARL_0 ≈ 465，即 465 筆正常交易才會誤觸發一次）。報告用的是絕對值而非 σ 的倍數，這意味著不同波動率的策略觸發靈敏度不同。**建議改為 σ 的倍數**。

2. **連續 15 筆虧損的硬性兜底太寬鬆**。以二項分佈計算：假設真實勝率 50%，連續 15 筆虧損的概率是 (0.5)^15 = 0.003%。這作為「不經 Agent 的硬兜底」合理。但如果我們的策略聲稱 70% 勝率，連續 15 筆虧損的概率是 (0.3)^15 ≈ 10^{-8}。在這種情況下等到 15 筆才暫停意味著策略早就徹底崩潰了。**建議：硬兜底門檻 = max(10, ceil(3 / ln(1/(1-win_rate))))**，即根據宣稱勝率動態調整。

---

## 5. OU Grid 間距公式

### 報告公式
```
grid_spacing_lower_bound = σ/√θ + 2 × fee_pct
```

### 數學驗證

OU 過程：dX = θ(μ - X)dt + σdW

穩態標準差 = σ / √(2θ)。報告寫的是 σ/√θ，差一個 √2。

**報告的公式有誤**。正確的推導：

```
OU 穩態分布：X ~ N(μ, σ²/(2θ))
穩態標準差 = σ / √(2θ)

Grid 間距的經濟邏輯：
  每次網格交易的預期利潤 = grid_spacing（價格走 1 格的利潤）
  每次交易的成本 = 2 × fee_pct（開 + 平）

  盈虧平衡：grid_spacing ≥ 2 × fee_pct
  加上波動率縮放：grid_spacing ≈ k × σ/√(2θ) + 2 × fee_pct

  其中 k 取決於你希望每格被觸發的頻率。k=1 約每 2.3 次穿越均值觸發一次。
```

正確公式：**`grid_spacing ≥ σ/√(2θ) + 2 × fee_pct`**

另外，`θ ≤ 0` 時必須暫停 Grid（報告附錄 C.2 正確指出了這點）。θ ≤ 0 意味著沒有均值回歸，Grid 會單邊累積虧損。這是 Grid 策略的生死線。

**與 Batch 9A 的關係**：Grid 策略尚未在我們的系統中實現。這是未來功能，與 Batch 9A 無直接交互。但 Batch 9A 的 round-trip 費用記錄機制可以直接為 Grid 的 fee_pct 提供準確數據。

---

## 6. 與 Batch 9A 的整體兼容性

### Batch 9A 已實施的 4 項

| 項目 | 報告中對應模型 | 兼容性 |
|------|---------------|--------|
| ATR 快/慢雙窗口 max(ATR_5, ATR_14) | EWMA Vol Estimator | **互補**。ATR 做止損，EWMA 做 regime/risk parity |
| 成本感知入場門檻 c_round/win_rate x 1.3 | Kelly 生存偏差修正 | **正交**。入場門檻管「開不開」，Kelly 管「開多大」 |
| 追蹤止損成本約束 activation-distance > c_round x 1.5 | 無直接對應 | **無衝突**。報告沒有碰追蹤止損設計 |
| round-trip 真實費用記錄 | PositionSizer 成本參數 | **支撐**。費用記錄為 Kelly/Grid/CUSUM 所有模型提供輸入 |

### 矛盾檢查

逐一掃描 10 項數學修正，**沒有發現與 Batch 9A 的矛盾**。

原因很簡單：Batch 9A 處理的是「止損參數 + 成本門檻」這個切面，報告的 10 項修正主要處理「倉位大小（Kelly）」、「策略健康（CUSUM）」、「波動率估計（EWMA）」、「regime 識別（Hurst）」、「Grid 間距（OU）」這些獨立維度。它們在不同的管線階段工作：

```
入場過濾（Batch 9A: 成本門檻）
  → Regime 識別（報告: Hurst + Hysteresis）
    → 倉位計算（報告: Kelly 分級 + 生存偏差）
      → 止損設置（Batch 9A: ATR 雙窗口）
        → 運行時監控（報告: CUSUM 衰減檢測）
          → 費用歸因（Batch 9A: round-trip 記錄）
```

每個模塊輸入輸出清晰，沒有循環依賴或參數衝突。

---

## 7. 採納建議

| # | 報告項目 | 建議 | 理由 |
|---|---------|------|------|
| 1 | Kelly 1/8→1/4 分級 + 生存偏差 | **採用** | 比我們計劃的 U-14 更完備，修正 current_run_time 語義後可用 |
| 2 | EWMA Vol Estimator | **採用，疊加** | 與 ATR 互補，用於 regime 分類和 risk parity，不替代 ATR |
| 3 | Hurst + Hysteresis | **採用，疊加** | 作為 MarketRegimeTracker 的輸入信號，修正 required_consecutive 按時間框架分級 |
| 4 | CUSUM StrategyHealthMonitor | **採用** | 我們完全沒有，需要 slack/threshold 改為 σ 的倍數 |
| 5 | OU Grid 間距 | **暫緩** | Grid 策略未實現；公式需修正 σ/√θ → σ/√(2θ) |
| 6 | HedgingEngine | **暫緩** | P2 優先級，當前無 delta 對沖需求 |

---

## 8. 必須修正的數學錯誤（報告中的）

| # | 位置 | 錯誤 | 正確值 |
|---|------|------|--------|
| 1 | §6.5 Grid 間距 | σ/√θ | σ/√(2θ) |
| 2 | B.1.2 Kelly 生存偏差 | current_run_time 語義不清 | 應為 total_observation_time |
| 3 | B.2.1 Hysteresis required=6 | 所有時間框架統一 6 | 按時間框架分級（1h→4, 4h→3, 1d→3） |
| 4 | §5.2 CUSUM slack=0.005 | 絕對值 | 應為 0.5σ（σ 為策略收益率標準差） |

以上 4 處是數學層面的問題，實施前必須修正。其餘模型數學正確。

---

> QC (Quantitative Consultant)
> 2026-04-03
