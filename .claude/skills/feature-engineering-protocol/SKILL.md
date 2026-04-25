---
name: feature-engineering-protocol
description: ML 特徵工程嚴謹性審計 — Look-ahead bias / target leakage / survivorship bias / cross-section leakage / time-zone leakage / re-sample boundary leak。MIT agent 主用，含偵測 SQL 範本。
allowed-tools: Read, Grep, Glob, Bash
---

# Feature Engineering Protocol（特徵工程嚴謹性手冊）

## 何時觸發

- MIT 收到「feature pipeline 設計」「ML 訓練 dataset 準備」「P1-7 C label 準備」「特徵不對勁、模型過擬合 RCA」
- 任何 `learning.exit_features` / `learning.bb_features` / 新 feature table 上線前
- ML training 後 IS Sharpe vs OOS Sharpe 差距 > 50% 的 RCA

## ★ 黃金法則

**特徵 leakage = 隱形殺手**：模型 IS 80% 準、OOS 50% 準（隨機）= leakage。
**回測 IS 看著漂亮 + Live 部署崩 = 80% 機率是 feature leakage**。

## 6 大 Leakage 類型

### 1. Look-ahead Bias（時序穿越）

**定義**：feature_t 用了 t 之後才能知道的資訊。

**OpenClaw 已驗實例**：
- `bb_breakout` F3 RETRACT：Donchian breach 用 rolling(N).max() **含 current bar**，breach 變成「current 是 N-bar max」必 mean revert（memory `feedback_indicator_lookahead_bias`）
- 修法：所有 rolling stat 必加 `.shift(1)` 或用 `.iloc[:-1]` 截 current bar

**偵測**：
```python
# 反例（leak）
df['bb_upper'] = df['close'].rolling(20).mean() + 2 * df['close'].rolling(20).std()
df['breach'] = df['close'] > df['bb_upper']  # current bar 在 rolling 內

# 正解（leak-free）
df['bb_upper'] = df['close'].shift(1).rolling(20).mean() + 2 * df['close'].shift(1).rolling(20).std()
df['breach'] = df['close'] > df['bb_upper']
```

### 2. Target Leakage（標籤穿越）

**定義**：feature 計算用了 target window 內的資訊。

**例**：預測「下一根 K 線方向」，feature 用 0:00-0:30 OHLC 平均，但 target window 是 0:00-1:00 → feature 已知 target window 一半。

**OpenClaw 警覺**：`exit_features` table 計算 `giveback_atr_norm` 必須用 entry tick 之前的 ATR（不能含 entry 後的 price action）。

**偵測**：
- 對每個 feature 列出「需要哪些 timestamp」
- 對每個 target 列出「target window 範圍」
- feature ts 重疊 target window → leak

### 3. Survivorship Bias（倖存偏差）

**定義**：訓練集只含「至今仍 live」的 symbol，已下市的不在內 → 模型過樂觀。

**OpenClaw 例**：Bybit delist 過的 symbol（如某些低交易量 perp）若不在 training set，模型沒學到 delisting risk。

**偵測**：
```sql
-- Symbol 完整性審計
SELECT symbol, min(ts), max(ts), 
       (max(ts) - min(ts)) / interval '1d' as tenure_days
FROM trading.fills 
WHERE engine_mode IN ('live', 'live_demo', 'demo')
GROUP BY symbol
ORDER BY tenure_days DESC;
-- 比對 Bybit 當前 active perp 列表，找出已 delist 的
```

### 4. Cross-Section Leakage（橫截面穿越）

**定義**：normalize / rank / standardize 用了**全 universe** 同期 cross-section 資訊（OK，當天可知），但若 standardize parameter（如 mean / std）用了**全期**資訊（含未來）→ leak。

**正解**：
```python
# 反例（用全期 mean / std）
df['z_score'] = (df['return'] - df['return'].mean()) / df['return'].std()

# 正解（expanding window）
df['z_score'] = (df['return'] - df['return'].expanding().mean()) / df['return'].expanding().std()
```

### 5. Time-Zone / Boundary Leakage

**定義**：跨 timezone 或跨 day boundary 時用了「未來」timezone 資料。

**OpenClaw 警覺**：funding settlement 整點 UTC 是固定的，但若 feature 計算用「local time of fill」可能跨 settlement 邊界拿後續 funding 資訊。

**檢查**：所有 timestamp 必統一 UTC。Bybit API 都是 ms-unix-UTC。

### 6. Re-sample Boundary Leakage

**定義**：從 1m k-line resample 到 5m / 1h，未 close 的 bar 被當完整 bar 用。

**例**：當前時間 12:03，5m bar 12:00-12:05 still building。若 model 用此 partial bar 的 OHLC → feature 含「未來 12:03-12:05」（其實是還沒到的）資訊。

**正解**：resample 後**只用已 closed bar**（`isClosed=true` 或 `now() > bar_end_time`）。

## 偵測 SQL 範本

### A. Look-ahead 偵測（per feature × per timestamp）
```sql
-- 對每個 feature 找出實際依賴的最後 timestamp
WITH feature_lookback AS (
  SELECT feature_name, 
         max(input_ts) as last_input_ts,
         feature_computed_at
  FROM learning.feature_metadata
  GROUP BY feature_name, feature_computed_at
)
SELECT feature_name, 
       count(*) FILTER (WHERE last_input_ts > feature_computed_at) as leakage_rows
FROM feature_lookback
GROUP BY feature_name;
-- leakage_rows > 0 = leak
```

### B. Target window 重疊偵測
```sql
-- feature_window_end 必須 < target_window_start
SELECT feature_name, target_name,
       count(*) FILTER (WHERE feature_window_end >= target_window_start) as overlap_count
FROM learning.feature_target_pairs
GROUP BY feature_name, target_name;
```

### C. Survivorship 偵測
```sql
-- 比對 training period 期間 active vs current active
WITH training_symbols AS (
  SELECT DISTINCT symbol FROM learning.training_set 
  WHERE date_range = 'last_90d'
),
current_active AS (
  SELECT DISTINCT symbol FROM trading.fills WHERE ts > now() - interval '7d'
)
SELECT 'in_training_not_current' as type, count(*)
FROM training_symbols t
LEFT JOIN current_active c USING (symbol)
WHERE c.symbol IS NULL;
-- > 0 個 → 至少 training 含 delisted symbol（好）
-- = 0 → 訓練集全是 survivor（壞，survivorship bias）
```

## 7 步審計工作流

1. **Feature inventory** — 列出所有 feature + 公式 + 依賴 timestamp
2. **Target inventory** — 列出 label + window
3. **Leakage type 6 維度逐查** — 對每 feature × target 跑 6 維檢查
4. **shift(1) 強制** — 任何 rolling stat 必加（OpenClaw 教訓）
5. **Resample 邊界** — 確認非 partial bar
6. **Cross-validation 驗 leakage 影響** — TimeSeriesSplit + purge + embargo（用 `time-series-cv-protocol` skill）
7. **IS vs OOS Sharpe 差距** — > 50% 必 RCA leak

## OpenClaw 特定核心

- **bb_breakout F3 RETRACT 教訓**：Donchian rolling.max() 含 current bar = leak（memory `feedback_indicator_lookahead_bias`）
- **exit_features.atr_pct fix**（P0-13）：原 per-tick `compute_atr_pct` deprecated，改用 `kline_manager.get_ohlcv("1m",20) + indicators::atr(14)` 持倉期 Wilder's ATR
- **engine_mode 過濾**：training 必含 'live' + 'live_demo'，paper 噪音不混
- **outcome_backfiller fix**（commit `5e2981d`）：timeframe '1' → '1m'，補回 ~267k row 的 outcome_*
- **P1-7 C labels 47/200**：當前 ML training set 樣本不足，feature engineering 即使做完也要等 labels 累積
- **maker_fill_rate 是合法 ML feature**：EDGE-P2-3 PostOnly 部署後 fee model 變化，maker fill 是動態 feature

## 反模式（見即 Reject）

- `df['close'].rolling(N).max()` 沒 shift(1)
- z-score / standardize 用全期 mean+std
- training set 不含已 delisted symbol
- resample 後用 partial bar（isClosed=false）
- timestamp 跨時區 / 跨 day 沒 UTC 統一
- feature timestamp > feature_computed_at（未來資訊穿越）
- IS Sharpe 80% / OOS Sharpe 50% 沒查 leakage
- 「我這樣寫 model accuracy 變高」沒驗證為何

## 輸出格式

```markdown
# MIT Feature Engineering Audit — <date>

## Feature inventory
| Feature | 公式 | 依賴 ts range | 計算 ts |

## Target inventory
| Target | window | label rule |

## 6 Leakage 類型逐項
| 類型 | 命中 features | 證據 |
| Look-ahead | | |
| Target leak | | |
| Survivorship | | |
| Cross-section | | |
| Time-zone | | |
| Resample boundary | | |

## shift(1) compliance
| feature | shift(1)? | 備註 |

## IS vs OOS Sharpe 差距
（如有 backtest 結果）IS: X / OOS: Y / gap: Z%

## 結論 + 修正
1. <具體 + 修法>

MIT AUDIT DONE: <report_path>
```
