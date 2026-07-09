# QC 審查報告：三層自適應參數架構
# QC Review: Three-Tier Adaptive Parameter Architecture

> 審查人：QC（Quantitative Consultant）
> 日期：2026-04-02
> 狀態：審查完成
> 結論：**PROCEED WITH REVISIONS** — 方向正確，但數學基礎需要加固，有若干設計缺陷需修正

---

## 0. Executive Summary

提案診斷準確：70% 勝率但淨虧損 ($-3.67) 的根因是 **交易成本超過毛利** 和 **止損/止盈參數與波動率不匹配**。三層自適應架構（Operator 硬邊界 → Agent 參數空間 → Per-symbol 動態值）的方向是正確的，但以下問題必須解決：

1. ATR-based 參數選值缺乏明確的數學推導，容易淪為「又一組 magic numbers」
2. 反饋迴路設計存在過擬合風險和因果混淆風險
3. 「預期利潤 < 2x 手續費不開倉」這條規則的閾值 2x 缺乏理論支撐
4. 遺漏了最根本的問題：**策略本身是否有 edge**

---

## 1. 數學合理性審查

### 1.1 ATR-based Stop 的數學依據

ATR (Average True Range) 用於度量近期實現波動率，將止損/止盈與 ATR 掛鈎有充分的理論基礎：

**合理之處：**
- ATR 是對 σ（局部波動率）的非參數估計，不依賴正態假設
- 止損距離 = k × ATR 確保不同波動率的幣種有相同的「噪音緩衝空間」
- 經典文獻（Kestner 2003, Kaufman 2013）已驗證 ATR-based stops 優於固定百分比 stops

**數學框架：**
```
設 σ_local = ATR / price（局部波動率百分比）
設 k_sl = 止損 ATR 倍數, k_trail = 追蹤止損 ATR 倍數, k_act = 追蹤啟動 ATR 倍數

則：
  hard_stop_distance    = k_sl × σ_local
  trailing_activation   = k_act × σ_local
  trailing_distance     = k_trail × σ_local

約束：k_trail < k_sl（追蹤比硬止損更緊）
約束：k_act > k_trail（啟動門檻大於追蹤距離，否則邏輯矛盾）
```

**問題：**
- 當前系統的 ATR 倍數（止損 1.5x、追蹤 1.2x）是拍腦袋定的，沒有經過交叉驗證
- ATR 本身有滯後性（14 期均值），在 regime 快速切換時反應遲鈍
- crypto 波動率的 jump component 很大，ATR 嚴重低估尾部風險

**建議修正：**
- k_sl 應通過 walk-forward 在 {1.0, 1.5, 2.0, 2.5, 3.0} 中搜索，找 parameter plateau（非 cliff）
- 加入 ATR 快/慢雙窗口（如 5 期 / 14 期），取 max 值作為保守估計
- 對 jump risk 補充：若最近 N 根 K 線有任何一根 body > 3σ，硬止損自動加寬 50%

### 1.2 自適應參數選值邏輯

提案中「根據 ATR/regime/歷史表現選擇最優參數」的邏輯，需要區分兩件事：

**確定性適應（可以做，且應該做）：**
- ATR → 止損距離：純粹的波動率縮放，不涉及預測，數學清晰
- Regime → 時間止損倍數：如 trending 給更多時間、volatile 快出場，已有文獻支持
- 手續費門檻：可以精算，不依賴歷史回測

**統計適應（需要極其謹慎）：**
- 「歷史 round-trip 表現 → 選參數」本質上是在做 in-sample 優化
- 20 筆交易的統計量什麼都說明不了，至少需要 200+ 筆同 regime 交易才有 0.8 的 power
- 把 round-trip 結果寫入 TruthSourceRegistry 再回讀 = 自我強化循環 = 過擬合的溫床

**結論：確定性適應立即實施，統計適應暫緩到數據充足後再啟用。**

### 1.3 「預期利潤 < 2x 手續費不開倉」規則

這條規則的方向對，但 2x 這個數字太隨意。正確的推導如下：

```
設：
  p = 策略勝率（已知 ≈ 70%，但樣本小，真實值的 95% CI 約 [47%, 87%]）
  R = avg_win / avg_loss（目前 ≈ 0.42）
  c_round = 開倉手續費 + 平倉手續費 + 滑點（兩次）
  E[PnL_gross] = p × avg_win - (1-p) × avg_loss
  E[PnL_net] = E[PnL_gross] - c_round

不開倉條件：E[PnL_net] < 0
即：E[PnL_gross] < c_round

保守起見（因為勝率估計有噪音），改為：
  不開倉條件：E[PnL_gross] < c_round / (1 - ε)
  其中 ε = 安全邊際（建議 0.3，即要求 gross profit 比成本多 30%）
```

**量化（以當前參數為例）：**
```
Bybit linear taker fee = 0.055% (each way)
Round-trip fee = 0.055% × 2 = 0.11%
滑點（BTC/ETH 大幣種）≈ 0.01% × 2 = 0.02%
c_round ≈ 0.13% of notional

若 notional = $100：c_round = $0.13
要求 gross profit > $0.13 / 0.7 = $0.186 → 需要 0.186% 的價格變動

加上 30% 安全邊際：需要 0.186 / 0.7 ≈ 0.27% 的價格變動
```

**結論：不應該用「2x 手續費」這種倍數，應該直接用 E[PnL_net] > 0 + 安全邊際。2x 對小幣種（手續費比例更大）可能不夠，對 BTC/ETH 可能太保守。**

### 1.4 更嚴謹的表述

把「預期利潤 < 2x 手續費不開倉」改為：

```
min_expected_move_pct = c_round_pct / estimated_win_rate × safety_margin
其中：
  c_round_pct = (taker_fee × 2 + slippage × 2) per symbol（可從 SLIPPAGE_TIERS 查）
  estimated_win_rate = max(0.3, 近 50 筆同 regime 的勝率)（下限 0.3 防除零/防過高估計）
  safety_margin = 1.3（固定，保守假設）

若 ATR_pct < min_expected_move_pct → 不開倉
```

這樣做的好處：
1. 不同幣種有不同的成本結構（SLIPPAGE_TIERS 已區分）
2. 勝率估計取近期數據 + 下限保護
3. 不依賴任何「魔法倍數」

---

## 2. 風控模型影響

### 2.1 引入的新風險

| 風險 | 嚴重度 | 說明 |
|------|--------|------|
| **過擬合** | HIGH | 統計適應部分。20 筆數據學到的「最優參數」幾乎肯定是噪音 |
| **Regime 誤判** | MEDIUM | 當前 regime 檢測是啟發式的，誤判 → 用錯參數 → 止損太寬或太窄 |
| **反饋迴路振盪** | MEDIUM | 連贏 → 放寬參數 → 遇到轉折 → 連虧 → 收緊 → 錯過反彈 → 循環 |
| **參數空間膨脹** | LOW | 每 symbol × regime × 5 參數 = 數百個動態值，debug 和審計難度增加 |
| **Operator 失去感知** | LOW | 參數在範圍內自動變化，Operator 可能不知道當前實際用了什麼值 |

### 2.2 邊界條件分析

**硬邊界衝突檢查（與 operator_risk_config.json 對照）：**

```
max_stop_loss_pct = 20.0（Operator）
若 ATR-based stop = 15% × regime_mult(1.5) = 22.5% → 超過硬邊界

修復：在 ATR 計算後，必須 min(atr_stop, operator_hard_cap × 0.8)
      （已有此邏輯，確認 ✅）
```

**追蹤止損啟動 vs 距離的邏輯一致性：**

```
若 activation = 0.3%（ATR 低的幣種）, distance = 0.2%
→ 啟動後只要回撤 0.2% 就退出
→ 實際上變成了一個「0.1% 利潤鎖定器」
→ 手續費 0.13% → 淨虧損

修復：追加約束 activation - distance > c_round_pct（啟動後鎖定的利潤必須 > 成本）
```

### 2.3 過擬合風險量化

假設系統有 5 個可調參數，每個 5 個取值，共 5^5 = 3,125 種組合。在 20 筆交易上搜索：

```
Deflated Sharpe Ratio 修正：
  SR_deflated = SR_observed - sqrt(2 × ln(N_trials)) / sqrt(N_trades)
  = SR - sqrt(2 × ln(3125)) / sqrt(20)
  = SR - sqrt(16.1) / 4.47
  = SR - 0.90

也就是說，觀察到的 Sharpe ratio 需要減去 0.90 才是 deflated 後的估計。
若 SR_observed < 0.90，你的策略可能完全沒有 edge。
```

**結論：在 N_trades < 200 的情況下，任何基於歷史交易的參數優化都不可信。**

---

## 3. 回測方法論

### 3.1 驗證自適應 vs 固定的正確方法

**不能做的事：**
- 拿同一段數據，先用固定參數跑一遍，再用自適應跑一遍，比較結果。這有嚴重的前視偏差。

**正確方法（Walk-forward + Anchored expanding window）：**
```
1. 準備至少 6 個月連續 K 線數據（不同 regime 都要覆蓋）
2. 分為 train/test 窗口（如 3 個月 train + 1 個月 test，sliding forward）
3. 每個窗口：
   a. 用 train 數據確定 ATR 統計量（均值、標準差、regime 分佈）
   b. 用 train 數據的「統計適應」參數（若啟用）
   c. 在 test 數據上前瞻性地跑策略（不允許回看）
   d. 記錄 test 期間的 PnL、Sharpe、MaxDD
4. 合併所有 test 期間的指標
5. 與固定參數（在全部 train 數據上取中位數作為固定值）做配對比較

統計檢驗：paired t-test on Sharpe across K folds, 或 bootstrap confidence interval
```

### 3.2 需要的回測框架增強

當前 BacktestEngine 是基本框架（純函數指標 + KlineAdapter）。驗證自適應參數需要：

1. **Walk-forward harness**：自動切分 train/test + 滾動 + 合併結果
2. **成本模型精確化**：必須用 per-symbol SLIPPAGE_TIERS，不能用全局平均值
3. **Regime 標註**：每根 K 線標記所處 regime（用事後精確標註，不是實時估計），用於分析 regime 維度的表現
4. **Parameter sensitivity surface**：對每個參數在 {-20%, -10%, 0%, +10%, +20%} 範圍繪製 Sharpe 曲面，檢查 plateau vs cliff
5. **Deflated Sharpe Ratio**：每次搜索後輸出 DSR，若 DSR < 0.5 自動 REJECT

### 3.3 最低數據要求

| 數據量 | 可信度 | 適用場景 |
|--------|--------|---------|
| < 50 筆 | 不可信 | 只能做確定性適應（ATR 縮放），不能做統計適應 |
| 50-200 筆 | 低信度 | 可以做粗略的 regime 分類表現統計，不能做參數搜索 |
| 200-500 筆 | 中信度 | 可以做 walk-forward，但 fold 數少（3-4），DSR 修正後可能不顯著 |
| > 500 筆 | 可信 | 可以做完整的參數搜索 + walk-forward + DSR |

**當前狀態：20 筆。離任何統計適應都差一個數量級。**

---

## 4. Alpha 角度分析

### 4.1 這個改動能否產生 Alpha？

直接回答：**不能。** 自適應參數不產生 alpha。Alpha 來自入場信號（entry signal），不來自風控參數（risk parameters）。

但是，這個改動可以做到兩件同樣重要的事：

1. **減少 alpha 的損耗 (alpha erosion)**：好的止損設計讓你保留策略本身的 edge，而不是被成本和噪音吃掉
2. **改善風險調整後收益 (risk-adjusted return)**：同樣的 alpha，更好的風控 → 更高的 Sharpe → 更快的資本增長

### 4.2 真正的問題：策略有 Edge 嗎？

回到數據：14W/6L，avg win $0.42，avg loss $0.995。

```
Expected value per trade = 0.7 × 0.42 - 0.3 × 0.995 = $0.294 - $0.299 = -$0.005
```

**這個策略在扣除成本前就已經接近零 edge。** 手續費只是讓它從「微正」變成「微負」。

根本問題是 **win/loss ratio 太低 (0.42)**。對於一個趨勢策略（MA Crossover），0.42 的 R:R 意味著贏利交易的持有期太短或者止損太遠。

**對比基準：**
| 策略類型 | 典型勝率 | 典型 R:R | 期望值方向 |
|---------|---------|---------|-----------|
| 趨勢跟蹤 | 30-40% | 2.0-5.0 | 低勝率高 R:R |
| 均值回歸 | 60-70% | 0.5-1.0 | 高勝率低 R:R |
| 當前 MA Crossover | 70% | 0.42 | 高勝率超低 R:R ← 不像任何一種 |

70% 勝率 + 0.42 R:R = 這不是一個趨勢策略的表現，這是一個「小波動隨便贏，大波動止損虧」的噪音交易器。

### 4.3 結構性 Edge 評估

OpenClaw 目前 5 個策略中，唯一有清晰結構性 edge 的是 **FundingRateArb**：

```
Edge 來源：永續合約 funding rate 結構性偏正（因為散戶偏多）
可論證性：有學術文獻支持（Solanki & Gupta 2022, Bianchi et al. 2023）
成本：spot + perp 雙腿手續費 = ~0.22%，但 funding 每 8h 結算一次
  若 funding rate = 0.01%/8h = 0.03%/day → 年化 ~11%
  扣手續費（進出各一次）= 0.22% → 需持倉 7.3 天以上才能覆蓋
可擴展性：高（BTC/ETH 流動性充足）
```

**建議：優先精算 FundingRateArb 的成本結構，而不是花精力優化 MA Crossover 的參數。**

---

## 5. 改進建議

### 5.1 立即可做（確定性適應，不依賴歷史數據）

**A. ATR 縮放止損和追蹤止損（提案中已包含，加固數學基礎）：**
```python
# 偽代碼 — 所有倍數用 walk-forward 驗證後的值
atr_pct = atr / price
hard_stop = max(operator_min_stop, min(k_sl * atr_pct, operator_max_stop * 0.8))
trail_activation = max(c_round_pct * 2.5, k_act * atr_pct)  # 保證啟動時已有足夠利潤
trail_distance = max(c_round_pct, min(k_trail * atr_pct, hard_stop * 0.8))
# 追加約束：trail_activation - trail_distance > c_round_pct
```

**B. 成本感知入場門檻（替代「2x 手續費」規則）：**
```python
c_round_pct = (taker_fee * 2 + slippage(symbol) * 2)
min_move_pct = c_round_pct / max(0.3, estimated_win_rate) * 1.3  # 安全邊際
if atr_pct < min_move_pct:
    reject_intent("insufficient_volatility_vs_cost")
```

**C. Regime-aware 參數表（確定性映射，不做統計搜索）：**

| Regime | 止損倍數 k_sl | 追蹤啟動 k_act | 追蹤距離 k_trail | 持倉上限 |
|--------|-------------|---------------|-----------------|---------|
| trending | 2.0 | 3.0 | 1.5 | 72h |
| volatile | 3.0 | 4.0 | 2.0 | 24h |
| ranging | 1.5 | 2.0 | 1.0 | 48h |
| squeeze | 1.0 | 1.5 | 0.8 | 12h |

（以上為初始值，需經 walk-forward 驗證後固定。注意這些值不應在運行時動態搜索。）

### 5.2 中期可做（需要數據積累）

**D. Per-regime 表現追蹤（不改參數，只記錄）：**
- 每筆 round-trip 記錄 regime + 參數組合 + 結果
- 積累 200+ 筆/regime 後，輸出 regime×策略 的 Sharpe 矩陣
- 人工審閱後決定是否調整 regime 映射表

**E. 止損距離 vs 成交結果的回歸分析：**
```
對已完成的 round-trips：
  y = pnl_net
  x = stop_distance_as_multiple_of_atr
  做 loess 平滑回歸，找 optimal k_sl 的粗略範圍
前提：N > 200，且覆蓋多個 regime
```

### 5.3 長期方向（策略層面，比參數調優重要 10 倍）

**F. 替換 MA Crossover 為有結構性 Edge 的策略：**

| 候選策略 | Edge 來源 | 實現難度 | 預期 Sharpe |
|---------|----------|---------|------------|
| Funding Rate Arb | 散戶偏多，funding 結構性偏正 | 中（需雙腿同步） | 1.0-2.0 |
| Volatility Mean Reversion | 隱含波動率 > 實現波動率（variance risk premium） | 高（需 option 支持） | 0.8-1.5 |
| Cross-exchange Basis | CEX 間價差回歸 | 中（需多交易所） | 0.5-1.0 |
| Liquidation Cascade Counter | 大量清算後的均值回歸 | 低（需清算數據） | 不確定 |

**G. Kelly Criterion 替代固定 risk_per_trade_pct：**
```
f* = (p × b - q) / b
其中 p = 勝率, q = 1-p, b = avg_win/avg_loss

當前：f* = (0.7 × 0.42 - 0.3) / 0.42 = (0.294 - 0.3) / 0.42 = -0.014
→ Kelly 建議：不要交易這個策略（f* < 0）。

若未來改善到 p=0.6, b=1.5：f* = (0.9 - 0.4) / 1.5 = 0.33 → 33% of bankroll
使用半 Kelly (f*/2 ≈ 16.7%) 作為保守估計
```

---

## 6. 16 條根原則合規性

### 原則 5：生存 > 利潤

| 評估項 | 結果 |
|--------|------|
| ATR-based stops 是否保護生存？ | **合規。** ATR 縮放讓止損與波動率匹配，減少「正常波動誤觸發」和「異常波動打穿」兩種風險 |
| 自適應是否可能危害生存？ | **條件合規。** 若統計適應在數據不足時啟用，可能學到噪音 → 放寬止損 → 增加尾部風險。必須設硬啟用門檻（200+ trades/regime） |
| 成本門檻是否過度限制？ | **合規。** 不開虧錢的交易就是保護生存 |

### 原則 11：Agent 最大自主權

| 評估項 | 結果 |
|--------|------|
| 三層架構是否給 Agent 足夠空間？ | **合規。** Operator 定範圍 + Agent 選值 = 正確的自主權模型 |
| 是否有 Agent 不能做但應該能做的事？ | 目前 Agent 不能選策略（只能用 MA Crossover），這才是真正限制自主權的瓶頸 |

### 原則 12：持續進化

| 評估項 | 結果 |
|--------|------|
| 反饋迴路設計是否支持學習？ | **部分合規。** round-trip → TruthSourceRegistry → 權重調整的設計方向對，但當前學習閉環（P0-GAP-1）尚未接通 |
| 過擬合是否會阻礙真正的學習？ | **風險存在。** 在數據不足時學到的「教訓」可能是錯的。建議所有統計學習結果標記 confidence_level 和 sample_size |

### 原則 13：成本感知

| 評估項 | 結果 |
|--------|------|
| 成本門檻是否正確建模？ | **改進空間。** 當前 cost_edge_ratio 只在 tab-ai.html 前端展示 + L2 觸發條件，未在入場時強制檢查。提案的成本感知入場門檻是正確的改進方向 |
| Per-symbol 成本是否考慮？ | **改進空間。** SLIPPAGE_TIERS 已按 24h turnover 分級，但手續費仍用全局默認值。不同 VIP 等級和不同品類的費率不同 |

### 整體合規結論

**方案與 4 條相關原則均不衝突**，但實施時需要注意：
- 統計適應部分必須設硬啟用門檻（原則 5 生存優先）
- Agent 參數空間的上下界必須在 Operator JSON 中明確定義（原則 11 框架內自主）
- 所有參數變化必須記錄審計日誌（原則 8 可解釋）
- 成本計算必須保守（taker fee，不假設 maker 成交）

---

## 7. 具體修改建議匯總

### MUST（不做就不應上線）

| # | 建議 | 理由 |
|---|------|------|
| M1 | 追加約束：`trail_activation - trail_distance > c_round_pct` | 否則追蹤止損鎖定的利潤 < 成本，追蹤成了擺設 |
| M2 | 把「2x 手續費」改為成本感知公式（§1.4） | 2x 是 magic number，不適應不同幣種 |
| M3 | 統計適應設硬啟用門檻：同 regime 200+ trades | 數據不足的統計學習 = 過擬合 |
| M4 | 所有動態參數值寫入 round-trip 記錄 | 否則無法事後分析哪組參數有效（原則 8） |

### SHOULD（強烈建議）

| # | 建議 | 理由 |
|---|------|------|
| S1 | ATR 取 max(ATR_fast, ATR_slow) | 單窗口 ATR 在 regime 切換時滯後 |
| S2 | 參數空間 `{min, max, default}` 加 `step` 字段 | 限制搜索粒度，減少過擬合 |
| S3 | 優先精算 FundingRateArb 成本模型 | 這是唯一有可論證 edge 的策略 |
| S4 | 加入 Kelly fraction 計算並在 GUI 展示 | 讓 Operator 直觀看到策略是否值得交易 |

### NICE-TO-HAVE（資源允許時）

| # | 建議 | 理由 |
|---|------|------|
| N1 | Walk-forward harness in BacktestEngine | 是驗證任何參數調整的基礎設施 |
| N2 | Deflated Sharpe Ratio 自動計算 | 防止 EvolutionEngine 輸出過擬合結果 |
| N3 | Jump detection（K 線 body > 3σ → 加寬止損） | 應對 crypto 尾部風險 |

---

## 8. 最終結論

方案方向正確，但需要區分兩類改動的性質：

1. **確定性適應**（ATR 縮放、成本門檻、regime 映射表）：數學清晰、不依賴歷史數據、立即可做。這部分解決「手續費吃掉利潤」和「參數與波動率不匹配」兩個問題。**建議立即實施。**

2. **統計適應**（歷史表現 → 參數調整 → TruthSourceRegistry 反饋）：在當前 20 筆數據的情況下，任何統計學習都不可信。**建議暫緩，先積累數據，架構預留但不啟用。**

然而，最根本的問題不是參數：**MA Crossover 在 crypto perpetual 上沒有可論證的 edge**。優化參數只是讓一個零 edge 策略虧得慢一點。系統的下一步應該是：

1. 精算 FundingRateArb 的完整成本模型（含 basis risk + execution timing）
2. 建立 walk-forward 回測框架
3. 用回測框架驗證所有 5 個策略的 out-of-sample 表現
4. 淘汰 Sharpe < 0.5 的策略，集中資源在有 edge 的策略上

**把精力花在尋找 alpha 上，而不是優化沒有 alpha 的策略的參數。**

---

> QC (Quantitative Consultant)
> 2026-04-02
