---
name: time-series-cv-protocol
description: 時序 ML 模型 cross-validation 設計 — Purged k-fold、Embargo、TimeSeriesSplit、Walk-forward variants、CSCV。MIT agent 主用，與 walk-forward-validation-protocol（QC 視角）互補：QC 看策略 alpha 顯著性，MIT 看 ML 模型訓練 CV 嚴謹性。
allowed-tools: Read, Grep, Glob, WebSearch
---

# Time Series CV Protocol（時序 CV 設計手冊）

> **優先序**：runtime RiskConfig TOML > Rust schema > CLAUDE.md > 治理 .md > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

## 何時觸發

- MIT 收到「ML training pipeline CV 設計」「sklearn TimeSeriesSplit 用法」「為何 OOS 退化」
- 任何 ML model（LightGBM / Transformer / TCN / 線性）訓練前
- ONNX export 前的 final validation
- P1-7 C labels 累積到 200+ 啟動 training pipeline 之前

## ★ 黃金法則

**時序資料禁用 KFold**（會 shuffle）：必用 TimeSeriesSplit 或 walk-forward。
**Purge + Embargo 是必要不是 optional**：未加就是 leakage。

> **C1.b cross-skill 邊界**：本 skill（MIT）跟 `walk-forward-validation-protocol`（QC）在 walk-forward / Purge / Embargo / CSCV 等技術細節有 ~50% 內容重疊。**同時觸發時職責分**：
> - **MIT 主負**：ML 模型訓練 CV 設計（sklearn TimeSeriesSplit / mlfinlab PurgedKFold / sample size for ML model 類別）
> - **QC 主負**：策略 alpha 顯著性（PSR / DSR / 統計檢定 / 多重比較修正）
> - 同時引用兩者的 audit task 應由 PM 明確指派 owner，避免雙頭判斷。

## 1. CV 方法對照表

| 方法 | 適用 | 缺點 | sklearn API |
|---|---|---|---|
| **KFold** | 時序資料 ❌ 禁用 | shuffle 後 future leak past | `sklearn.model_selection.KFold` |
| **TimeSeriesSplit** | 時序基本 baseline | 默認無 purge / embargo | `sklearn.model_selection.TimeSeriesSplit` |
| **Walk-Forward Anchored** | 累積學習 | 後期 train fold 巨大 | 自寫 |
| **Walk-Forward Rolling** | 固定 lookback | regime 切換場景 | 自寫 |
| **Purged k-fold (Lopez de Prado)** | 含 label window 重疊 | 計算複雜 | `mlfinlab` 套件 |
| **CSCV (Combinatorially Symmetric CV)** | PBO 計算 | 樣本要求大 | 自寫 |

## 2. Purge + Embargo（Lopez de Prado, AFML Ch.7）

### 2.1 Purge（淨化）
**問題**：label `y_t` 由 `[t, t+H]` 區間決定（如 H 期未來 return 方向），train fold 中接近 test fold start 的 sample，其 label 已含 test 區間資訊 → leak。

**Purge 動作**：train fold 中刪除「label window 與 test fold 任何重疊」的 sample。

```
test_start = T
purge_range = [T - H, T]   # label horizon
train_keep = train_set 中 label_end_ts < T - H 的 sample
```

### 2.2 Embargo（禁忌期）
**問題**：feature 含 autocorrelation，test fold 開始後立刻 train 下一個 fold 仍含 nearby contamination。

**Embargo 動作**：test fold 結束後，跳 N 期再開 train。

```
test_end = T'
embargo_pct = 0.01   # 1% of total samples
train_resume = T' + embargo_periods
```

### 2.3 OpenClaw 適用
- `exit_features` 中 H = exit horizon (如持倉期 60s-3600s)
- Embargo % = 0.5-1% of total samples（Lopez de Prado 推薦）
- 1m timeframe + 5 strat × 25 symbol → embargo ≈ 1d 期

## 3. 樣本量規劃

| 模型類別 | 最少 train sample | 對應 OpenClaw 場景 |
|---|---|---|
| **Linear regression** | ≥ 10 × n_features | 25 features → ≥ 250 |
| **LightGBM (small)** | ≥ 1000 | P1-7 C 47/200 不夠 |
| **LightGBM (typical)** | ≥ 10000 | 5 strat × 25 symbol × 1m × 30d 過 |
| **Transformer** | ≥ 100k | 1m 級 ~半年才夠 |
| **TCN / N-BEATS** | ≥ 50k | 1m ~3 個月 |

當 P1-7 C labels 不足 §3 表閾值（具體進度動態查 `psql -c "SELECT count(*) FROM learning.exit_features WHERE engine_mode IN ('live','live_demo')"`）→ **不訓練，只準備 pipeline**。**禁寫死「47/200」等 snapshot 數字當決策依據** — 隨時間累積會失真。

## 4. CV split 設計實例

### 4.1 OpenClaw 1m exit-features 模型 baseline
```python
from sklearn.model_selection import TimeSeriesSplit

# 取 90d demo + live_demo data
df = load_features(engine_mode__in=['demo', 'live_demo'], days=90)
df = df.sort_values('ts').reset_index(drop=True)

# 5 fold time series split with embargo + purge
tscv = TimeSeriesSplit(n_splits=5, gap=embargo_periods)

for train_idx, test_idx in tscv.split(df):
    # purge: 刪 train 中 label_end_ts >= test_start 的 sample
    train_idx_purged = [i for i in train_idx 
                         if df.iloc[i]['label_end_ts'] < df.iloc[test_idx[0]]['ts']]
    
    X_train = df.iloc[train_idx_purged][features]
    y_train = df.iloc[train_idx_purged]['target']
    X_test = df.iloc[test_idx][features]
    y_test = df.iloc[test_idx]['target']
    
    # train + eval
    ...
```

### 4.2 Walk-Forward Rolling（regime 切換場景）
```python
window_train = 90_days
window_test = 30_days
stride = 30_days

t = data.start
while t + window_train + window_test < data.end:
    train = data[t : t+window_train]
    test = data[t+window_train+embargo : t+window_train+window_test]
    # purge train tail
    train = train[train['label_end_ts'] < test['ts'].min()]
    yield train, test
    t += stride
```

### 4.3 Anchored Expanding（長期穩定 alpha）
```python
window_train_min = 90_days
window_test = 30_days
stride = 30_days

t = data.start + window_train_min
while t + window_test < data.end:
    train = data[: t]   # 累積
    test = data[t+embargo : t+window_test]
    train = train[train['label_end_ts'] < test['ts'].min()]
    yield train, test
    t += stride
```

OpenClaw 推薦：**Walk-Forward Rolling**（crypto regime 快）。

## 5. CSCV（Combinatorially Symmetric Cross-Validation）

Lopez de Prado et al. (2014, 2017)。用於 PBO 計算（Probability of Backtest Overfitting）。

**步驟**：
1. 把 sample 切 N 份（建議 N=16）
2. 從 N 中選 N/2 為 train（C(N, N/2) 個組合）
3. 每個組合：train 上找最佳策略，test 上看排名
4. PBO = best-on-train 在 test 中是否 > median 的概率

PBO < 0.5 = 模型未過擬合主導。

## 6. CV 結果評估

### 6.1 Per-fold metrics
- AUC / accuracy / log-loss / R²
- 對 trading：Sharpe / hit rate / drawdown
- **Per-fold variance** 比 mean 重要（穩定性）

### 6.2 IS vs OOS gap
- gap < 30% = 健康
- gap 30-50% = warning
- gap > 50% = 過擬合或 leakage（用 `feature-engineering-protocol` skill RCA）

### 6.3 Cross-fold consistency
- 對 5 fold 的 metric 算 std
- std / mean > 0.5 → 不穩定，不上線

## 7. 與 sklearn / scikit-learn 套件對照

```python
# sklearn 內建
from sklearn.model_selection import TimeSeriesSplit
# 默認 gap=0（無 embargo），需手動傳 gap

# mlfinlab（Lopez de Prado）
from mlfinlab.cross_validation import PurgedKFold
pkf = PurgedKFold(n_splits=5, samples_info_sets=label_end_ts, pct_embargo=0.01)

# 自寫 walk-forward（複雜時用）
```

## 8. 工作流（10 步）

1. **資料 sort by ts** — 必要前置
2. **Label end_ts 列** — 每 sample 的 label window 結束時間
3. **CV 方法選擇**（默認 Walk-Forward Rolling）
4. **N folds 設計**（5-10）
5. **Window 設計**（train 90d / test 30d / embargo 1d）
6. **Purge 邏輯**（train_label_end < test_start）
7. **Per-fold metrics 計算**
8. **Cross-fold consistency**（mean ± std）
9. **IS vs OOS gap**（用同期 train sample 算 IS）
10. **CSCV / PBO**（K ≥ 10 model variants 時做）

## OpenClaw 特定核心

- **engine_mode IN ('live', 'live_demo')**：training 過濾必含兩者
- **exit_features atr_pct fix**（P0-13）：用 `kline_manager.get_ohlcv("1m",20) + indicators::atr(14)`
- **P1-7 C labels 累積中**：訓練 pipeline ready 但資料量隨時間變動（命令拿，不寫死）
- **`outcome_*` NULL → 1m timeframe fix**（commit `5e2981d`）：歷史回填行數命令查（`SELECT count(*) FROM learning.exit_features WHERE outcome_pnl IS NOT NULL`），不寫死
- **TimescaleDB hypertable**：support fast time-range query for CV split
- **embargo recommended 1d 起跳**（**非治理硬規範**）：1m × 1440 bars/day；具體 embargo size 依 label horizon + autocorrelation 動態調整

## Cross-Skill 互引（避免重述）

- **C1.b QC 視角 = 策略 alpha 顯著性**（PSR / DSR / Bonferroni / PBO）走 `walk-forward-validation-protocol`；本 skill = MIT 視角，**ML 模型訓練 CV 設計**（sklearn / mlfinlab）
- **C1.c feature 設計 + leakage**：feature-side 6 leakage 類型（look-ahead / target / survivorship 等）走 `feature-engineering-protocol`，本 skill 補 split-side leakage（purge / embargo）
- **pipeline 成熟度評級**：本 skill CV 設計通過 ≠ pipeline live；走 `ml-pipeline-maturity-audit` 看 4 維度 + 5 階段

## 反模式（見即 Reject）

- `KFold`（time series 禁用）
- `TimeSeriesSplit(gap=0)` 用在 label 含 H 期 horizon 場景
- 沒 purge train 中 label window 重疊
- 訓練前 shuffle 時序資料
- IS sample 跟 OOS sample 重疊（無 embargo）
- 5 fold metric 全用 mean 不看 std
- IS 80% / OOS 60% 不查 leakage
- N=2 fold 還宣稱「驗證過」
- Anchored expanding 對 regime 切換 crypto 用（用 rolling）

## 輸出格式

```markdown
# MIT Time Series CV Audit — <model_name> · <date>

## CV 設計
- 方法：Walk-Forward Rolling / Anchored / Purged k-fold
- N folds: X
- train_window: Y_days
- test_window: Z_days
- embargo: W periods
- purge logic: <describe>

## 樣本量
| Fold | train_n | test_n | features_n |

## Per-fold metrics
| Fold | AUC | Sharpe | drawdown | hit_rate |

## Cross-fold 穩定性
mean: X / std: Y / std/mean: Z

## IS vs OOS gap
IS: A / OOS: B / gap: C%

## CSCV / PBO（如做）
PBO = D

## 結論 + 建議
Approve / Conditional / Reject

MIT AUDIT DONE: <report_path>
```
