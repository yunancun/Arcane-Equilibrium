---
name: feature-engineering-protocol
description: MIT agent 主用：設計 feature pipeline、準備 ML 訓練 dataset、新 feature 表上線前、或 IS 漂亮 OOS 崩（疑 leakage）的 RCA 時必讀。
allowed-tools: Read, Grep, Glob, Bash
---

# Feature Engineering Protocol（特徵工程嚴謹性手冊）

> Authority typed matrix 正本見 `16-root-principles-checklist` 頭部（`.codex/agent_registry_v1.json` 定義）：只在同類內比較，跨類標 DRIFT/CONFLICT，runtime 不得合法化 policy denial；即時內容依 authority class 與 fresh evidence 取得，本 skill 不寫死。
> 以內建知識為底：leakage 類型學的通用定義與偵測法不在本檔重述；本檔只列本專案的已驗實例、判準與 SSOT 指針。

## 何時觸發

- MIT 收到「feature pipeline 設計」「ML 訓練 dataset 準備」「P1-7 C label 準備」「特徵不對勁、模型過擬合 RCA」
- 任何 `learning.exit_features` / `learning.bb_features` / 新 feature table 上線前
- ML training 後 IS Sharpe vs OOS Sharpe 差距 > 50% 的 RCA

## ★ 黃金法則

**特徵 leakage = 隱形殺手**：IS 80% 準、OOS 50% 準（隨機）= leakage。**回測 IS 漂亮 + Live 崩 = 80% 機率是 feature leakage**。

## 6 大 Leakage 類型 — OpenClaw 判準與已驗實例

（各類型通用定義與偵測法靠內建知識；逐 feature × target 檢查時全 6 類都要過。）

### 1. Look-ahead Bias（時序穿越）
- **OpenClaw 已驗實例**：`bb_breakout` F3 RETRACT — Donchian breach 用 rolling(N).max() **含 current bar**，breach 變成「current 是 N-bar max」必 mean revert（memory `feedback_indicator_lookahead_bias`）
- 修法：所有 rolling stat 必加 `.shift(1)` 或 `.iloc[:-1]` 截 current bar；審計時要求並列 leak-free 版對比

### 2. Target Leakage（標籤穿越）
- **OpenClaw 警覺**：`exit_features` 的 `giveback_atr_norm` 必須用 entry tick 之前的 ATR（不能含 entry 後 price action）
- 偵測：對每 feature 列「依賴的 timestamp」、對每 target 列「window 範圍」；feature ts 重疊 target window → leak

### 3. Survivorship Bias（倖存偏差）
- **OpenClaw 例**：Bybit delist 過的 symbol 若不在 training set，模型沒學到 delisting risk
- 偵測 SQL：`SELECT symbol, min(ts), max(ts) FROM trading.fills WHERE engine_mode IN ('live','live_demo','demo') GROUP BY symbol` 後比對 Bybit 當前 active perp 列表；訓練集全是 survivor = 壞

### 4. Cross-Section Leakage（橫截面穿越）
- 同期 cross-section normalize OK；standardize parameter（mean / std）用**全期**資訊 = leak → 改 expanding window

### 5. Time-Zone / Boundary Leakage
- **OpenClaw 警覺**：funding settlement 整點 UTC 固定，feature 用「local time of fill」可能跨 settlement 邊界拿後續 funding 資訊
- 檢查：所有 timestamp 統一 UTC；Bybit API 都是 ms-unix-UTC

### 6. Re-sample Boundary Leakage
- 從 1m resample 到 5m / 1h 時，未 close 的 partial bar 被當完整 bar 用 = leak
- 正解：resample 後**只用已 closed bar**（`isClosed=true` 或 `now() > bar_end_time`）

## 偵測 SQL 注意

偵測 SQL 範本中的表名（`learning.feature_metadata` / `learning.feature_target_pairs` / `learning.training_set` 等）為**示意 schema**；執行前先以 `information_schema.tables` 驗證存在，不存在則在報告標註並改用實際表名。核心查法：feature 依賴的最後 input_ts 不得晚於 feature_computed_at；feature_window_end 必須 < target_window_start；training set 與 current active symbol 差集檢驗 survivorship。

## 7 步審計工作流

1. **Feature inventory** — 列出所有 feature + 公式 + 依賴 timestamp
2. **Target inventory** — 列出 label + window
3. **Leakage type 6 維度逐查** — 對每 feature × target 跑 6 維檢查
4. **shift(1) 強制** — 任何 rolling stat 必加（OpenClaw 教訓）
5. **Resample 邊界** — 確認非 partial bar
6. **CV 驗 leakage 影響** — TimeSeriesSplit + purge + embargo（用 `time-series-cv-protocol`）
7. **IS vs OOS Sharpe 差距** — > 50% 必 RCA leak

## 穩定 ML feature rule（不會 drift）

training filter 必含 'live' + 'live_demo'（不混 paper）；任何 rolling stat 必加 `.shift(1)` leak-free；resample 後只用 closed bar（`isClosed=true`）；feature ts 必早於 target window start（不重疊）。table 名 / column / row 量必跑 SQL 取真值。

## Cross-Skill 互引（避免重述）

- **C1.c pipeline 成熟度評級**：本 skill 看單表 leakage（feature 設計層面）；4 維度評級 + 5 階段走 `ml-pipeline-maturity-audit`
- **C1.h schema 設計 + Guard A/B/C migration**：走 `db-schema-design-financial-time-series`
- **CV 設計 / Purge / Embargo**：走 `time-series-cv-protocol`（MIT）— 本 skill 解 feature-side leakage，time-series-cv 解 split-side leakage

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

## shift(1) compliance
| feature | shift(1)? | 備註 |

## IS vs OOS Sharpe 差距
（如有 backtest 結果）IS: X / OOS: Y / gap: Z%

## 結論 + 修正
1. <具體 + 修法>

MIT returns an immutable `role_fragment_v1` with `payload_kind=finding_fragment_v1` for the task closure; no automatic report or memory append.
```
