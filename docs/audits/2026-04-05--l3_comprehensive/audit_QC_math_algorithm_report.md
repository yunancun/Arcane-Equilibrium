# QC 量化審計報告 — 數學/算法正確性 + 硬編碼值審查

**審計員：** QC（量化顧問）
**日期：** 2026-04-05
**範圍：** OpenClaw 交易系統全部數學公式、風控算法、ML 模組
**審計版本：** Rust 859 tests · Python 1075 tests · 全綠

---

## 目錄

1. [風控計算 (Risk Calculations)](#1-風控計算)
2. [Kelly 準則 (Kelly Criterion)](#2-kelly-準則)
3. [成本門控 (Cost Gate)](#3-成本門控)
4. [損益計算 (PnL Computation)](#4-損益計算)
5. [ATR 計算 (ATR Calculation)](#5-atr-計算)
6. [倉位管理 (Position Sizing)](#6-倉位管理)
7. [Thompson Sampling](#7-thompson-sampling)
8. [CPCV 交叉驗證](#8-cpcv-交叉驗證)
9. [Optuna TPE](#9-optuna-tpe)
10. [PSI/ADWIN 漂移檢測](#10-psiadwin-漂移檢測)
11. [黑天鵝檢測 (Black Swan)](#11-黑天鵝檢測)
12. [特徵收集器 (Feature Collector)](#12-特徵收集器)
13. [止損計算 (Stop Loss)](#13-止損計算)
14. [Guardian 守護者檢查](#14-guardian-守護者檢查)
15. [硬編碼值總表](#15-硬編碼值總表)
16. [總結與建議](#16-總結與建議)

---

## 1. 風控計算

### 1.1 check_order_allowed（訂單准入）

**文件：** `rust/openclaw_core/src/risk/checks.rs:57-119`

**5 項檢查（優先級序）：**

| # | 檢查 | 公式 | 判定 |
|---|------|------|------|
| 1 | 日損限制 | `daily_loss_pct >= max_daily_loss_pct` | ✅ 正確 |
| 2 | 槓桿限制 | `leverage > max_leverage` | ✅ 正確 |
| 3 | 單倉大小 | `(qty × price / balance) × 100 > max_single_position_pct` | ✅ 正確 |
| 4 | 總曝險 | `current_exposure_pct >= max_total_exposure_pct` | ✅ 正確 |
| 5 | 相關曝險 | `correlated_exposure_pct >= max_correlated_exposure_pct` | ✅ 正確 |

**數學正確性：** ✅ 全部正確

**設計要點：**
- 減倉永遠通過（符合原則 #5 生存 > 利潤）✅
- balance=0 跳過單倉百分比檢查（防除零）✅
- 所有閾值來自 `RiskManagerConfig`（可配置）✅

**⚠️ 注意事項：**
- `correlated_exposure_pct` 在 `intent_processor.rs:302` 中硬編碼為 `0.0`（標記 "Phase C wiring"），意味著相關曝險檢查永遠不會觸發。這是已知的技術債務，非 Bug。

### 1.2 check_position_on_tick（9 項 Tick 級檢查）

**文件：** `rust/openclaw_core/src/risk/checks.rs:154-265`

| # | 檢查 | 公式/邏輯 | 判定 |
|---|------|-----------|------|
| 1 | 硬止損 | `pnl_pct <= -max_stop_loss_pct` | ✅ |
| 2 | 動態止損 | `pnl_pct <= -dyn_stop`（ATR+regime+anti-cluster） | ✅ |
| 3 | 止盈 | `pnl_pct >= max_take_profit_pct × rm.tp`（regime 乘數） | ✅ |
| 4 | 追蹤止損 | `(peak - current) >= distance` 且 `peak >= activation` | ✅ |
| 5 | 時間止損 | `holding_hours >= max_hours × rm.time` | ✅ |
| 6 | 成本邊際 | `cost_ratio >= 0.8 AND pnl > 0` | ✅ |
| 7 | 會話回撤 | `session_drawdown >= max_session_drawdown_pct` → HaltSession | ✅ |
| 8 | 連續虧損 | `consecutive >= count` → SetCooldown | ✅ |
| 9 | 日損限制 | `daily_loss >= max_daily_loss_pct` → HaltSession | ✅ |

**數學正確性：** ✅ 全部正確

**⚠️ 設計觀察：**
- 成本邊際檢查（#6）只在持倉有利潤時觸發 — 邏輯上合理（虧損倉位不應因成本比率平倉，應留給止損處理）。
- 動態止損 base = `max_stop_loss_pct × 0.6`（硬止損的 60%）— 這個 `0.6` 是硬編碼的（見硬編碼值總表）。

---

## 2. Kelly 準則

**文件：** `rust/openclaw_engine/src/ml/kelly_sizer.rs`

### 2.1 Kelly 公式

```
f* = W - (1-W)/R
其中 R = avg_win / avg_loss, W = win_rate
```

**判定：** ✅ 正確 — 這是標準 Kelly 公式。

### 2.2 分數 Kelly + 樣本量分層

| 交易數 | Kelly 分數 | 判定 |
|--------|-----------|------|
| < 50   | f*/8      | ✅ 非常保守，適合樣本不足 |
| < 200  | f*/6      | ✅ 合理過渡 |
| >= 200 | f*/4      | ✅ 學術建議為 1/4 Kelly 作為上限 |

**數學正確性：** ✅ — Thorp (2008) 建議分數 Kelly 介於 1/4 到 1/2 之間。永不使用 full Kelly 是正確的保守選擇。

### 2.3 ATR 波動率調整

```
vol_multiplier = (0.02 / atr_pct).clamp(0.5, 1.5)
kelly_qty = kelly_qty × vol_multiplier
```

**判定：** ✅ 正確 — 參考 ATR% = 2% 作為基準。高波動時縮小倉位（multiplier < 1），低波動時放大（multiplier > 1，最高 1.5 倍）。clamp 防止極端情況。

**⚠️ 硬編碼值：**
- `0.02`（參考 ATR%）— 應為可配置（見總表 HC-K1）
- `0.5` / `1.5`（clamp 範圍）— 應為可配置（見總表 HC-K2）
- `0.01`（負 Kelly 時的最低風險百分比）— 應為可配置（見總表 HC-K3）

### 2.4 負 Kelly 處理

```
if kelly_full <= 0.0:
    使用 balance × 0.01 / price 作為最小倉位
```

**判定：** ⚠️ 可質疑 — 負 Kelly 意味著沒有正期望值（edge 為負）。學理上應該零倉位。然而從系統設計角度，保留極小倉位（1%）用於數據收集是合理的折中。建議增加配置項，允許零倉位選項。

---

## 3. 成本門控

### 3.1 CostGate（round-trip 成本估算）

**文件：** `rust/openclaw_core/src/cost_gate.rs`

```
round_trip_cost_pct = (taker_fee + slippage) × 2 × 100 / 100
                    = (taker_fee + slippage) × 2
```

**判定：** ✅ 正確 — `(taker_fee_pct + slippage_pct) * 2.0 / 100.0 * 100.0` 中 `/100.0 * 100.0` 互相抵消，等效於 `(fee + slip) × 2`。雖然寫法冗余（乘除相消），但結果正確。

**⚠️ 注意：** 代碼中 `/100.0 * 100.0` 是數學冗余操作（行 69），建議簡化為 `(tier.taker_fee_pct + tier.slippage_pct) * 2.0` 以提高可讀性。

### 3.2 CostGate（成本-波動性比較）

```
min_move_pct = round_trip_cost / win_rate × 1.3
if ATR < min_move: reject
```

**判定：** ✅ 經濟學上合理 — 這是 "breakeven move" 的概念：
- `cost / win_rate` = 每次交易需要的最低回報以在期望值上覆蓋成本
- `× 1.3` = 30% 安全邊際
- win_rate clamp [0.3, 1.0] 防止極端值

### 3.3 Gate 3 Cost Gate（intent_processor 中的 QC 公式）

**文件：** `rust/openclaw_engine/src/intent_processor.rs:317-359`

```
expected_profit = ATR × confidence × qty
round_trip_fee = notional × 2 × fee_rate  （其中 notional = qty × price）
reject if: expected_profit < k × round_trip_fee
```

**判定：** ⚠️ 可質疑 — 公式在概念上有合理性但存在維度問題：

**問題分析：**
- `ATR` 的單位是**價格**（如 BTC 的 ATR 可能是 $500）
- `confidence` 是 [0, 1] 的概率
- `expected_profit = ATR × confidence × qty` = 價格 × 概率 × 數量 = 美元

這實際上在計算「如果價格移動了一個 ATR 幅度，以 confidence 概率，我們能賺多少」。這是 EV 的**粗略上界估計**。

**嚴格來說應為：**
```
EV = win_rate × avg_win - (1 - win_rate) × avg_loss
```

但在信號層面只有 confidence（近似 win_rate），沒有 avg_win/avg_loss，所以用 ATR 作為代理是合理的簡化。

**最終判定：** ✅ 經濟上合理作為 Phase 3b 的保守近似。

**⚠️ 硬編碼值：**
- `K_PAPER = 1.5`（行 325）— 應為可配置
- `K_LIVE` 未實現（TODO 註釋）
- `MIN_CONFIDENCE = 0.15`（行 324）— 應為可配置
- `fee_rate = 0.00055`（fallback，行 343）— 已有動態費率機制，OK

---

## 4. 損益計算

**文件：** `rust/openclaw_core/src/execution.rs:104-133`

### 4.1 未實現損益

```
Long:  (current_price - entry_price) × qty
Short: (entry_price - current_price) × qty
```

**判定：** ✅ 正確 — 這是 linear/inverse perpetual 的標準公式。

### 4.2 已實現損益

```
Long:  (exit_price - entry_price) × qty - entry_fee - exit_fee
Short: (entry_price - exit_price) × qty - entry_fee - exit_fee
```

**判定：** ✅ 正確

### 4.3 PnL 百分比（tick_pipeline）

**文件：** `rust/openclaw_engine/src/tick_pipeline.rs:826-829`

```rust
let pct = |a, b| if p.entry_price <= 0.0 { -999.0 }
    else if p.is_long { (a - b) / b * 100.0 }
    else { (b - a) / b * 100.0 };
let pnl_pct = pct(price, p.entry_price);
```

**判定：** ✅ 正確
- Long: `(price - entry) / entry × 100`
- Short: `(entry - price) / entry × 100`
- 除零保護（entry <= 0.0 → -999.0）✅

**⚠️ 品類適用性：**
- 對 **linear perpetual** 和 **spot**：✅ 公式完全正確
- 對 **inverse perpetual**：⚠️ 需要注意 — inverse 合約的 PnL 應以 BTC 計而非 USD。但當前系統標記 `option 未來`，inverse 支持的 PnL 計算需在實際接入時驗證。以百分比形式表達（相對於入場價的百分比變化）本身對 inverse 也是正確的。

---

## 5. ATR 計算

**文件：** `rust/openclaw_core/src/risk/price_tracker.rs:93-123`

### 5.1 ATR 公式

```
ATR_pct = mean(|return_i|) × 100
其中 return_i = (price[i] - price[i-1]) / price[i-1]
```

**判定：** ⚠️ 可質疑 — 這是**平均絕對回報率**（Average Absolute Return），而非標準的 Wilder ATR。

**差異分析：**

| 指標 | 標準 Wilder ATR | 本系統實現 |
|------|----------------|-----------|
| 輸入 | OHLC K 線 | Tick 價格序列 |
| True Range | max(H-L, |H-C_prev|, |L-C_prev|) | |P_i - P_{i-1}| |
| 平均方法 | EMA (α=1/14) | 簡單算術平均 |
| 用途 | K 線級波動率 | Tick 級波動率 |

**結論：** 這不是教科書上的 Wilder ATR，而是一種 **tick-level 平均絕對回報率**。作為風控用的波動率代理指標，在 tick 粒度下（無 OHLC）是合理的替代方案。但名稱可能造成誤解。

**建議：** 考慮在文檔中明確說明這是 "Average Absolute Return" 而非 Wilder ATR。在指標引擎（`openclaw_core/src/indicators/volatility.rs`）中，如果使用 K 線數據，應實現標準 Wilder ATR。

**⚠️ 硬編碼值：**
- `DEFAULT_WINDOW_SECS = 300`（5 分鐘窗口）— 見總表 HC-A1
- `DEFAULT_MIN_SAMPLES = 10` — 見總表 HC-A2
- `SPIKE_THRESHOLD_SIGMA = 3.0` — 見總表 HC-A3

### 5.2 Spike Detection

```
sigma = |current_price - mean| / std_dev
spike if sigma >= 3.0
```

**判定：** ✅ 正確 — 標準 z-score 離群值檢測。3σ 閾值合理（正態假設下覆蓋 99.7%）。但加密市場呈肥尾分佈，實際觸發頻率可能高於預期。

**注意：** 使用的是 population variance（除以 n 而非 n-1）。對於窗口 ≥ 10 個樣本，差異可忽略。

---

## 6. 倉位管理

### 6.1 ATR Position Sizing

**文件：** `rust/openclaw_core/src/stop_manager.rs:199-214`

```
risk_amount = balance × (risk_per_trade_pct / 100)
stop_distance = atr × atr_multiplier
qty = risk_amount / stop_distance
qty = clamp(qty, min_qty, max_qty)
```

**判定：** ✅ 正確 — 標準 ATR 倉位管理公式。邏輯：
1. 確定願意承擔的美元風險
2. 確定 ATR 倍數的止損距離
3. 計算使得 "如果觸及止損，損失恰好等於風險金額" 的倉位大小

**⚠️ 邊界保護：** `atr <= 0.0 || atr_multiplier <= 0.0 → min_qty` ✅

### 6.2 P1 Hard Cap

**文件：** `rust/openclaw_engine/src/intent_processor.rs:285-287`

```
p1_max_qty = balance × p1_risk_pct / price
final_qty = min(kelly_qty, p1_max_qty)
```

**判定：** ✅ 正確 — 簡單的風險資本百分比限制。`p1_risk_pct` clamp [0.001, 0.20] 防止極端配置。

**⚠️ 硬編碼值：**
- `DEFAULT_P1_RISK_PCT = 0.02`（2%）— 已可配置 ✅
- P1 clamp 上限 `0.20`（20%）— 見總表 HC-P1

---

## 7. Thompson Sampling

**文件：** `program_code/ml_training/thompson_sampling.py`

### 7.1 NIG 共軛更新公式

```
lam_n   = lam + 1
mu_n    = (lam × mu + x) / lam_n
alpha_n = alpha + 0.5
beta_n  = beta + 0.5 × lam × (x - mu)² / lam_n
```

**判定：** ✅ 正確 — 這是 Normal-Inverse-Gamma 共軛先驗的標準 Bayesian 更新公式。參見 Murphy (2007) "Conjugate Bayesian Analysis of the Gaussian Distribution"。

### 7.2 NIG 抽樣

```
Step 1: sigma² ~ InverseGamma(alpha, beta)
        = 1 / Gamma(alpha, scale=1/beta)
Step 2: mu ~ Normal(posterior.mu, sigma² / lambda)
```

**判定：** ✅ 正確 — 標準 NIG 層級抽樣流程。

**⚠️ 注意：** `np_rng.gamma(shape=alpha, scale=1.0/beta)` 產生 Gamma(alpha, 1/beta)，然後取倒數得到 InverseGamma(alpha, beta)。這在數學上是正確的。

### 7.3 Empirical Bayes 初始化

```
mu_0   = mean(returns)
lam_0  = 3.0
alpha_0 = 3.0
beta_0 = var(returns) × (alpha_0 - 1) = var × 2
```

**判定：** ✅ 基本正確

- `alpha_0 = 3.0` 確保方差的期望值存在（需 alpha > 2）✅
- `lam_0 = 3.0` — 合理的先驗強度（3 筆新交易就能偏離先驗）✅
- `beta_0 = var × (alpha - 1)` — 使得 E[sigma²] = beta/(alpha-1) = var ✅

**⚠️ 硬編碼值：**
- `lam_0 = 3.0` — 見總表 HC-T1
- `alpha_0 = 3.0` — 見總表 HC-T2
- `floor_trials = 10`（exploitation_floor）— 見總表 HC-T3
- `_MIN_LAMBDA = 1e-6` / `_MIN_ALPHA = 1.001` / `_MIN_BETA = 1e-9` — 數值安全常數，保持硬編碼合理

### 7.4 exploitation_floor 機制

```
if total_trials < floor_trials:
    選 mu 最高的臂（純利用）
else:
    正常 Thompson Sampling
```

**判定：** ✅ 合理 — 防止在數據極少時做純探索。

---

## 8. CPCV 交叉驗證

**文件：** `program_code/ml_training/cpcv_validator.py`

### 8.1 Purge + Embargo

```
purge_before: ts < test_start AND ts + purge_sec > test_start
purge_after:  ts > test_end   AND ts - purge_sec < test_end
embargo_before: ts >= test_start - embargo_sec AND ts < test_start
embargo_after:  ts > test_end AND ts <= test_end + embargo_sec
```

**判定：** ✅ 正確 — 完整的雙向 purge + embargo 實現。符合 de Prado (2018) "Advances in Financial Machine Learning" 中的 CPCV 規範。

### 8.2 功效估計

```
power ≈ 1 - exp(-samples_per_fold × effect_size² / 4)
```

**判定：** ⚠️ 可質疑 — 這是一個近似公式，並非精確的統計功效計算（精確計算需要 scipy.stats 的非中心 t 分佈）。作為快速估算可以接受，但：
- `effect_size = 0.3` 是固定值（Cohen's d = 0.3 = 小效應量）
- 除數 4 是經驗近似

**建議：** 在文檔中標註這是近似估計，或在 Phase 4 中使用精確的功效分析。

### 8.3 Embargo 映射

| 策略類型 | Embargo 小時 | 判定 |
|---------|-------------|------|
| trending | 24h | ✅ 趨勢策略需較長去相關時間 |
| reversion | 4h | ✅ 回歸策略反應快 |
| arb | 8h | ✅ 套利中等 |
| grid | 72h | ✅ 網格策略持倉時間長 |

**判定：** ✅ 合理的領域知識映射。

**⚠️ 硬編碼值：**
- `n_folds = 4` — 見總表 HC-C1
- `power_threshold = 0.5` — 見總表 HC-C2
- `min_samples_per_fold = 30` — 見總表 HC-C3
- `label_window_hours = 4.0` — 見總表 HC-C4
- `effect_size = 0.3` — 見總表 HC-C5

---

## 9. Optuna TPE

**文件：** `program_code/ml_training/optuna_optimizer.py`

### 9.1 EV_net 公式

```
EV_net = p × (avg_win - c_win) - (1-p) × (avg_loss + c_loss)
其中 c_win = fee_rate × avg_win, c_loss = fee_rate × avg_loss
```

**判定：** ⚠️ 可質疑 — 手續費建模有簡化：
- `c_win = fee_rate × avg_win` — 這裡 fee 應該基於 **notional**（名義價值），而非 PnL。手續費 = fee_rate × (price × qty)，與盈虧大小無關。
- 但如果 `avg_win` 近似為名義價值的比例，則這是一階近似。

**嚴格正確的公式：**
```
EV_net = p × avg_win - (1-p) × avg_loss - avg_notional × fee_rate × 2
```

**當前簡化的影響：** 會略微高估 EV（因為手續費被低估了）。在 paper trading 階段影響有限。

### 9.2 離線目標函數

```python
ev = compute_ev_net(fills)  # 全部 fills 計算，不分試驗
perturbation = Σ 0.001 × (1 - |2×norm_pos - 1|)
return ev + perturbation
```

**判定：** ⚠️ 可質疑 — 當前離線模式下所有試驗使用相同的 fills 數據，僅通過微小擾動區分。這意味著：
1. `best_params` 實際上是擾動的產物，而非真正的參數優化結果
2. EV 基本相同，參數選擇接近隨機

**但代碼中已明確標註這是 "placeholder heuristic"，live 模式下將使用真實的 per-trial fills。** 作為 Phase 3b 的佔位實現可以接受。

**⚠️ 硬編碼值：**
- `n_trials = 30` — 見總表 HC-O1
- `min_fills_required = 80` — 見總表 HC-O2
- `fee_rate = 0.0006`（compute_ev_net 默認值）— 見總表 HC-O3
- `perturbation 係數 0.001` — 見總表 HC-O4

---

## 10. PSI/ADWIN 漂移檢測

**文件：** `rust/openclaw_engine/src/database/drift_detector.rs`

### 10.1 PSI 公式

```
PSI = Σ (P_i - Q_i) × ln(P_i / Q_i)
```

**判定：** ✅ 正確 — 標準 Population Stability Index 公式。epsilon 平滑處理空 bin 正確。

### 10.2 ADWIN 變化檢測

```
左右子窗口比較：
- 計算 mean1, mean2, var1, var2
- SE = sqrt(var1/n1 + var2/n2)
- z_threshold = sqrt(-2 × ln(delta/4))
- 觸發如果 |mean1 - mean2| > z_threshold × SE
```

**判定：** ✅ 基本正確 — 這是 Welch t-test 的近似，結合了 ADWIN 的 delta 邊界。

**數學細節：**
- `z_threshold = sqrt(-2 × ln(delta/4))`：當 delta=0.05 時，z ≈ sqrt(-2 × ln(0.0125)) ≈ sqrt(8.76) ≈ 2.96。這比標準 z=1.96 (alpha=0.05) 更保守，這是合理的（ADWIN 需要更嚴格的邊界因為多次測試）。
- 使用 population variance (除以 n) 而非 sample variance (除以 n-1)。對大窗口差異可忽略。

**3-consecutive majority vote：** ✅ 好的設計 — 防止單次誤報觸發漂移告警。

### 10.3 Block Bootstrap PSI

```
重採樣塊大小 = 4（默認）
自助次數 = 100
計算 5th/95th 百分位作為置信區間
```

**判定：** ✅ 正確 — 塊自助法保留時間序列依賴結構。

**⚠️ 硬編碼值：**
- ADWIN `delta = 0.05` — 見總表 HC-D1
- ADWIN `min_width = 50` — 見總表 HC-D2
- ADWIN `consecutive_required = 3` — 見總表 HC-D3
- Bootstrap `block_size = 4` — 見總表 HC-D4
- `burnin_days = 30` — 從 DatabaseConfig 讀取 ✅

---

## 11. 黑天鵝檢測

**文件：** `rust/openclaw_engine/src/database/black_swan_detector.rs`

### 11.1 四信號投票

| 信號 | 公式 | 判定 |
|------|------|------|
| MAD | `\|return - median\| > 6 × MAD` | ✅ 正確，6× MAD ≈ 4σ（正態等價） |
| Correlation | `avg_pairwise_\|corr\| > 0.85` | ✅ 合理的市場傳染檢測 |
| Volume | `current_vol > 5 × avg_vol` | ✅ 簡潔有效 |
| Velocity | `\|single_bar_return\| > daily_range / velocity_bars` | ✅ 合理 |

### 11.2 MAD 計算

```
MAD = median(|x_i - median(x)|)
```

**判定：** ✅ 正確 — 標準 MAD 定義。比標準差更 robust（不受極端值影響）。

### 11.3 Pearson Correlation

```
corr = Σ(da × db) / sqrt(Σda² × Σdb²)
```

**判定：** ✅ 正確 — 標準 Pearson 相關係數。denom < 1e-15 時返回 0.0（防除零）✅

### 11.4 投票嚴重級別

| 投票數 | 級別 | 判定 |
|--------|------|------|
| 0-1 | None | ✅ |
| 2 | Observe | ✅ |
| 3 | Upgrade | ✅ |
| 4 | Defensive | ✅ |

**判定：** ✅ 合理的階梯式回應。

**⚠️ 硬編碼值：**
- `mad_threshold = 6.0` — 見總表 HC-B1
- `corr_threshold = 0.85` — 見總表 HC-B2
- `volume_multiplier = 5.0` — 見總表 HC-B3
- `velocity_bars = 15` — 見總表 HC-B4
- `max_return_window = 720`（~12h）— 見總表 HC-B5
- `max_volume_window = 43200`（~30 天）— 見總表 HC-B6
- MAD 最低數據量 `30` — 見總表 HC-B7
- Volume 最低數據量 `100` — 見總表 HC-B8
- Correlation 窗口 `30` — 見總表 HC-B9

---

## 12. 特徵收集器

**文件：** `rust/openclaw_engine/src/feature_collector.rs`

### 12.1 34 維特徵向量

| 索引 | 特徵 | 判定 |
|------|------|------|
| 1-2 | SMA(20), SMA(50) | ✅ |
| 3-4 | EMA(12), EMA(26) | ✅ |
| 5 | RSI(14) | ✅ |
| 6-8 | MACD(macd, signal, histogram) | ✅ |
| 9-13 | Bollinger(upper, middle, lower, bandwidth, %B) | ✅ |
| 14-15 | ATR(14)(atr, atr_percent) | ✅ |
| 16-17 | ATR(5)(atr, atr_percent) | ✅ |
| 18-19 | Stochastic(K, D) | ✅ |
| 20-21 | KAMA(kama, efficiency_ratio) | ✅ |
| 22-24 | ADX(adx, +DI, -DI) | ✅ |
| 25-26 | Hurst(hurst, regime_encoded) | ✅ |
| 27-28 | EWMA Vol(vol, vol_regime_encoded) | ✅ |
| 29 | Volume Ratio | ✅ |
| 30-33 | Donchian(upper, lower, middle, width) | ✅ |
| 34 | Current Price | ✅ |

**判定：** ✅ 34 維正確計數。debug_assert 驗證維度一致性。

**⚠️ 注意事項：**
- 缺失值處理：`Option<T>` → 使用默認值（0.0 或 50.0 for RSI, 0.5 for Hurst）。這對 ML 模型可能不理想（0.0 和真實的 0 無法區分）。建議未來考慮使用 NaN 或特殊標記值。
- Regime 編碼為 integer（1.0, 2.0, 3.0）直接放入特徵向量。對 tree-based 模型（LightGBM）可以，但對 DL 模型建議使用 one-hot。

**⚠️ 硬編碼值：**
- `FEATURE_DIM = 34` — 與結構耦合，保持硬編碼合理
- `DEFAULT_BUFFER_CAPACITY = 3000` — 見總表 HC-F1
- RSI 默認值 `50.0` — 合理（中性值）
- Hurst 默認值 `0.5` — 合理（random walk）

---

## 13. 止損計算

**文件：** `rust/openclaw_core/src/stop_manager.rs`

### 13.1 Hard Stop

```
Long:  stop_price = entry × (1 - hard_stop_pct/100)
Short: stop_price = entry × (1 + hard_stop_pct/100)
```

**判定：** ✅ 正確

### 13.2 Trailing Stop

```
Long:  trail_price = best_price × (1 - trail_pct/100)
Short: trail_price = best_price × (1 + trail_pct/100)
```

**判定：** ✅ 正確 — 僅在持倉有利潤時追蹤（`best_price > entry_price` for long）。

### 13.3 Take Profit

```
Long:  tp_price = entry × (1 + tp_pct/100)
Short: tp_price = entry × (1 - tp_pct/100)
```

**判定：** ✅ 正確

### 13.4 Time Stop

```
max_hold_ms = hours × 3,600,000
held_ms = now_ms - entry_ts_ms  （飽和減法）
觸發如果 held_ms >= max_hold_ms
```

**判定：** ✅ 正確 — 使用 `saturating_sub` 防止時間戳下溢。

### 13.5 Dynamic Stop（anti-cluster）

**文件：** `rust/openclaw_core/src/risk/stops.rs`

```
1. base = base_stop_pct × regime_mult.stop
2. cap = hard_stop × 0.8
3. 有 ATR: effective = max(base, min(atr × 1.5, cap))
4. offset = anti_cluster_offset(symbol, ts_ms)  // [-0.15, +0.15]
5. result = (effective × (1 + offset)).max(0.1)
```

**判定：** ✅ 算法正確且設計良好

- cap 為 hard stop 的 80% 留餘裕 ✅
- anti-cluster 使用確定性雜湊（可重現）✅
- 下限 0.1% 防止接近零的止損 ✅
- ATR 乘以 1.5（ATR 的 1.5 倍作為止損距離是常見做法）✅

**⚠️ 硬編碼值：**
- `0.6`（base = hard_stop × 0.6，在 checks.rs:183）— 見總表 HC-S1
- `0.8`（cap = hard_stop × 0.8，在 stops.rs:51）— 見總表 HC-S2
- `1.5`（atr_stop = atr × 1.5，在 stops.rs:55）— 見總表 HC-S3
- `0.30`（anti-cluster 範圍 ±0.15，在 stops.rs:21）— 見總表 HC-S4
- `0.1`（最小止損百分比下限，在 stops.rs:66）— 見總表 HC-S5

---

## 14. Guardian 守護者檢查

**文件：** `rust/openclaw_core/src/guardian.rs`

### 14.1 四項檢查

| # | 檢查 | 邏輯 | 判定 |
|---|------|------|------|
| 1 | 方向衝突 | 同 symbol 反向持倉存在 → +0.4 risk | ✅ |
| 2 | 同向持倉數 | `same_dir_count >= max_same_direction_positions` → +0.3 risk | ✅ |
| 3 | 槓桿上限 | `ratio > 2.0` → reject; `1.0-2.0` → modify | ✅ |
| 4 | 回撤限制 | `drawdown > max_drawdown_pct` → +0.35 risk | ✅ |

### 14.2 Verdict 邏輯

```
if (方向衝突 || 過高槓桿 || 回撤突破 || 持倉過多) && risk_score >= 0.3:
    Rejected
elif 有修改:
    Modified
else:
    Approved
```

**判定：** ✅ 正確

**⚠️ 硬編碼值：**
- risk_score 加權值 `0.4, 0.3, 0.4, 0.15, 0.35` — 見總表 HC-G1
- 判定閾值 `risk_score >= 0.3` — 見總表 HC-G2
- 槓桿雙倍閾值 `leverage_ratio > 2.0` — 見總表 HC-G3
- `modification_size_factor = 0.5`（預設配置中）— 已可配置 ✅
- `modification_leverage_cap = 2.0`（預設配置中）— 已可配置 ✅

---

## 15. 硬編碼值總表

### ❌ 關鍵（應立即可配置化）

| ID | 文件 | 行 | 當前值 | 描述 | 風險等級 |
|----|------|-----|--------|------|---------|
| HC-S1 | risk/checks.rs | 183 | `0.6` | 動態止損 base = hard_stop × 0.6 | **高** — 直接影響止損距離 |
| HC-S2 | risk/stops.rs | 51 | `0.8` | 動態止損 cap = hard_stop × 0.8 | **高** — 止損上限 |
| HC-S3 | risk/stops.rs | 55 | `1.5` | ATR → 止損距離乘數 | **高** — 止損核心參數 |
| HC-CG1 | intent_processor.rs | 325 | `1.5` | Cost Gate K_PAPER | **高** — 成本門檻倍數 |
| HC-CG2 | intent_processor.rs | 324 | `0.15` | MIN_CONFIDENCE 硬地板 | **高** — 信號過濾閾值 |

### ⚠️ 中等（建議可配置化）

| ID | 文件 | 行 | 當前值 | 描述 | 風險等級 |
|----|------|-----|--------|------|---------|
| HC-K1 | kelly_sizer.rs | 143 | `0.02` | Kelly ATR 參考百分比 | 中 |
| HC-K2 | kelly_sizer.rs | 143 | `0.5-1.5` | Kelly vol clamp 範圍 | 中 |
| HC-K3 | kelly_sizer.rs | 123 | `0.01` | 負 Kelly 最低風險% | 中 |
| HC-G1 | guardian.rs | 107,119,129,139,149 | 0.4/0.3/0.4/0.15/0.35 | Guardian risk score 加權 | 中 |
| HC-G2 | guardian.rs | 159 | `0.3` | Guardian reject 閾值 | 中 |
| HC-G3 | guardian.rs | 124 | `2.0` | 槓桿 reject 的雙倍因子 | 中 |
| HC-S4 | risk/stops.rs | 21 | `0.30` | Anti-cluster 範圍 (±0.15) | 中 |
| HC-S5 | risk/stops.rs | 66 | `0.1` | 最小止損百分比下限 | 中 |
| HC-B1 | black_swan_detector.rs | 58 | `6.0` | MAD 閾值倍數 | 中 |
| HC-B2 | black_swan_detector.rs | 60 | `0.85` | 相關性閾值 | 中 |
| HC-B3 | black_swan_detector.rs | 62 | `5.0` | 成交量異常倍數 | 中 |
| HC-B4 | black_swan_detector.rs | 64 | `15` | Velocity 窗口 bars | 中 |
| HC-P1 | intent_processor.rs | 114 | `0.20` | P1 risk clamp 上限 | 中 |

### 📝 低風險（可保持硬編碼或延後配置化）

| ID | 文件 | 行 | 當前值 | 描述 |
|----|------|-----|--------|------|
| HC-A1 | price_tracker.rs | 7 | `300` | ATR 窗口秒數 |
| HC-A2 | price_tracker.rs | 10 | `10` | ATR 最少樣本 |
| HC-A3 | price_tracker.rs | 13 | `3.0` | Spike σ 閾值 |
| HC-B5 | black_swan_detector.rs | 107 | `720` | Return 窗口 bars |
| HC-B6 | black_swan_detector.rs | 108 | `43200` | Volume 窗口 bars |
| HC-B7 | black_swan_detector.rs | 169 | `30` | MAD 最低數據量 |
| HC-B8 | black_swan_detector.rs | 246 | `100` | Volume 最低數據量 |
| HC-B9 | black_swan_detector.rs | 218 | `30` | Correlation 窗口 |
| HC-T1 | thompson_sampling.py | 86 | `3.0` | NIG lam_0 |
| HC-T2 | thompson_sampling.py | 87 | `3.0` | NIG alpha_0 |
| HC-T3 | thompson_sampling.py | 255 | `10` | Exploitation floor trials |
| HC-C1 | cpcv_validator.py | 51 | `4` | CPCV n_folds |
| HC-C2 | cpcv_validator.py | 61 | `0.5` | Power 閾值 |
| HC-C3 | cpcv_validator.py | 62 | `30` | 每折最低樣本 |
| HC-C4 | cpcv_validator.py | 60 | `4.0` | 標籤窗口小時 |
| HC-C5 | cpcv_validator.py | 196 | `0.3` | 效應量（Effect size） |
| HC-D1 | drift_detector.rs | 116 | `0.05` | ADWIN delta |
| HC-D2 | drift_detector.rs | 116 | `50` | ADWIN min_width |
| HC-D3 | drift_detector.rs | 116 | `3` | ADWIN 連續檢測要求 |
| HC-D4 | (使用時傳入) | — | `4` | Bootstrap block_size |
| HC-O1 | optuna_optimizer.py | 91 | `30` | TPE 試驗次數 |
| HC-O2 | optuna_optimizer.py | 92 | `80` | 最低成交數 |
| HC-O3 | optuna_optimizer.py | 234 | `0.0006` | EV_net 默認費率 |
| HC-O4 | optuna_optimizer.py | 506 | `0.001` | 擾動係數 |
| HC-F1 | feature_collector.rs | 21 | `3000` | Feature buffer 容量 |

### CostGate 成本分層（cost_gate.rs:31-57）

| Volume 閾值 | Slippage | Taker Fee | 判定 |
|-------------|----------|-----------|------|
| >$1B | 0.01% | 0.055% | ✅ BTC/ETH 合理 |
| >$100M | 0.02% | 0.055% | ✅ 大盤幣合理 |
| >$10M | 0.05% | 0.055% | ✅ 中盤幣合理 |
| >$1M | 0.15% | 0.055% | ✅ 小盤幣合理 |
| <$1M | 0.30% | 0.055% | ✅ 微盤幣合理 |

**注意：** `taker_fee_pct = 0.055%` 對所有分層都一樣。這是 Bybit 默認 taker 費率。VIP 等級不同費率需要動態獲取（已有 API-fetched fee 機制）。整個 COST_TIERS 表應可配置化（目前是 const）。

### Regime 乘數（risk/config.rs:100-128）

| Regime | Stop 乘數 | TP 乘數 | Time 乘數 | 判定 |
|--------|----------|---------|----------|------|
| trending | 1.0 | 1.5 | 1.5 | ✅ 趨勢中放寬止盈和持倉時間 |
| volatile | 1.5 | 0.8 | 0.8 | ✅ 高波動放寬止損、收緊止盈 |
| ranging | 0.7 | 0.7 | 0.8 | ✅ 震盪中收緊兩端 |
| squeeze | 0.6 | 0.5 | 1.0 | ✅ 壓縮中極度收緊 |
| default | 1.0 | 1.0 | 1.0 | ✅ 中性 |

**這 12 個乘數全部硬編碼在 match 語句中。** 應提取為可配置結構。

### Execution 常數（execution.rs）

| 常數 | 值 | 判定 |
|------|-----|------|
| TAKER_FEE_RATE | 0.00055 | ✅ Bybit 默認，有動態覆蓋機制 |
| MAKER_FEE_RATE | 0.0002 | ✅ Bybit 默認 |
| Slippage tiers | 5 層 | ✅ 合理估算 |

---

## 16. 總結與建議

### 數學正確性總評

| 模組 | 判定 | 說明 |
|------|------|------|
| Risk Calculations | ✅ 正確 | 9 項檢查邏輯清晰正確 |
| Kelly Criterion | ✅ 正確 | 標準分數 Kelly，保守適當 |
| Cost Gate | ✅ 正確 | 經濟學合理，維度一致 |
| PnL Computation | ✅ 正確 | 標準公式，除零保護完整 |
| ATR Calculation | ⚠️ 注意 | 非 Wilder ATR 但作為 tick 代理合理 |
| Position Sizing | ✅ 正確 | 標準 ATR-based sizing |
| Thompson Sampling | ✅ 正確 | NIG 共軛更新公式精確 |
| CPCV | ✅ 正確 | 符合 de Prado 規範 |
| Optuna TPE | ⚠️ 注意 | 離線模式為佔位，live 需重新驗證 |
| PSI/ADWIN | ✅ 正確 | PSI 標準，ADWIN 保守合理 |
| Black Swan | ✅ 正確 | 4 信號獨立投票，統計學穩健 |
| Feature Collector | ✅ 正確 | 34 維對齊驗證 |
| Stop Loss | ✅ 正確 | 所有方向和邊界處理正確 |
| Guardian | ✅ 正確 | 風險評分和裁決邏輯一致 |

### 關鍵發現

1. **❌ 無嚴重數學錯誤** — 所有核心公式在數學上是正確的或合理的近似。

2. **⚠️ 5 個高風險硬編碼值**（HC-S1, HC-S2, HC-S3, HC-CG1, HC-CG2）直接影響交易決策的核心參數，建議優先配置化。

3. **⚠️ Optuna 離線目標函數** 目前是佔位實現，所有試驗共享同一組 fills。Phase 4 進入 live 模式前必須重新設計。

4. **⚠️ EV_net 手續費建模** 簡化了 notional-based 費用為 PnL-based 費用，會略微高估 EV。

5. **⚠️ ATR 命名** — PriceHistoryTracker 中的 "ATR" 實際是 Average Absolute Return，非 Wilder ATR。文檔應澄清。

6. **📝 Regime 乘數**（12 個值）全部硬編碼在 match 語句中。雖然當前值合理，但應提取為可配置結構以支持運行時調整。

### 優先級建議

**P0（高風險，建議 Phase 4 前完成）：**
- 將 HC-S1/S2/S3/CG1/CG2 配置化
- Regime 乘數提取為可配置結構

**P1（中風險，Phase 4 期間完成）：**
- Guardian risk score 加權和 reject 閾值配置化
- Kelly ATR 參考值和 clamp 配置化
- Black Swan 4 個閾值配置化
- CostGate COST_TIERS 配置化

**P2（低風險，可延後）：**
- ATR 窗口參數配置化
- Thompson Sampling 先驗強度配置化
- CPCV 功效估計改用精確公式
- Feature Collector 缺失值改用 NaN 標記

---

*報告結束。QC 不寫代碼，僅驗證數學正確性和識別配置化需求。*
