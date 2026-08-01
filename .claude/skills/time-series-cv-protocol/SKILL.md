---
name: time-series-cv-protocol
description: MIT agent 主用：設計 ML 訓練 CV、任何 model 訓練前、OOS 退化排查、ONNX export 前驗證時讀；策略 alpha 顯著性（QC）歸 walk-forward-validation-protocol。
allowed-tools: Read, Grep, Glob, Bash, WebSearch
---

# Time Series CV Protocol（時序 CV 設計手冊）

> Authority typed matrix 正本見 `16-root-principles-checklist` 頭部（`.codex/agent_registry_v1.json` 定義）：只在同類內比較，跨類標 DRIFT/CONFLICT，runtime 不得合法化 policy denial；即時內容依 authority class 與 fresh evidence 取得，本 skill 不寫死。
> 以內建知識為底：KFold/TimeSeriesSplit 通識、walk-forward 概念、sklearn API 不在本檔重述；本檔只列本專案的判準、教訓與 SSOT 指針。
> **本檔為 Purged k-fold / Embargo / CSCV 機制細節唯一正本**（`walk-forward-validation-protocol` 指向此處）。

## 何時觸發

- MIT 收到「ML training pipeline CV 設計」「為何 OOS 退化」
- 任何 ML model（LightGBM / Transformer / TCN / 線性）訓練前
- ONNX export 前的 final validation
- exit-label 累積到 200+ 啟動 training pipeline 之前

## ★ 黃金法則

**時序資料禁用 KFold**（會 shuffle）：必用 TimeSeriesSplit 或 walk-forward。
**Purge + Embargo 是必要不是 optional**：未加就是 leakage。

> **C1.b cross-skill 邊界**：本 skill（MIT）跟 `walk-forward-validation-protocol`（QC）職責分：**MIT 主負** ML 模型訓練 CV 設計（TimeSeriesSplit / PurgedKFold / ML sample size）；**QC 主負**策略 alpha 顯著性（PSR / DSR / 統計檢定 / 多重比較修正）。同時引用兩者的 audit task 應由 PM 明確指派 owner，避免雙頭判斷。

## 1. Purge + Embargo（唯一正本；Lopez de Prado, AFML Ch.7）

### 1.1 Purge（淨化）
**問題**：label `y_t` 由 `[t, t+H]` 區間決定，train fold 中接近 test fold start 的 sample，其 label 已含 test 區間資訊 → leak。
**動作**：train fold 中刪除「label window 與 test fold 任何重疊」的 sample：`train_keep = label_end_ts < test_start − H` 之前的 sample。

### 1.2 Embargo（禁忌期）
**問題**：feature 含 autocorrelation，test fold 結束後立刻接 train 仍含 nearby contamination。
**動作**：test fold 結束後跳 N 期再開 train；embargo_pct 建議 0.5–1% of total samples。

### 1.3 OpenClaw 適用
- `exit_features` 中 H = exit horizon（如持倉期 60s-3600s）
- 1m timeframe + 5 strat × 25 symbol → embargo ≈ 1d 期
- 實作要點：`TimeSeriesSplit(gap=embargo_periods)` + 手動 purge（train 中刪 `label_end_ts >= test_start` 的 sample）；sklearn 默認 `gap=0` 無 embargo，label 含 H 期 horizon 場景必手動傳

## 2. 樣本量規劃

| 模型類別 | 最少 train sample | 對應 OpenClaw 場景 |
|---|---|---|
| **Linear regression** | ≥ 10 × n_features | 25 features → ≥ 250 |
| **LightGBM (small)** | ≥ 1000 | exit-label 早期不夠 |
| **LightGBM (typical)** | ≥ 10000 | 5 strat × 25 symbol × 1m × 30d 過 |
| **Transformer** | ≥ 100k | 1m 級 ~半年才夠 |
| **TCN / N-BEATS** | ≥ 50k | 1m ~3 個月 |

labels 不足閾值（進度動態查 `psql -c "SELECT count(*) FROM learning.exit_features WHERE engine_mode IN ('live','live_demo')"`）→ **不訓練，只準備 pipeline**。**禁寫死「47/200」等 snapshot 數字當決策依據**。

## 3. CV 方法選型（OpenClaw 判準）

- **OpenClaw 推薦：Walk-Forward Rolling**（crypto regime 快；anchored expanding 不適合）
- 建議起點：train 90d / test 30d / stride 30d / embargo 1d + purge train tail（`train['label_end_ts'] < test['ts'].min()`）
- Purged k-fold / 自寫 walk-forward 的通用寫法靠內建知識；mlfinlab 開源版已停滯，套件選型以當前維護狀態為準，建議自寫或審查後選用

## 4. CSCV（唯一正本）

Lopez de Prado et al. (2014, 2017)，用於 PBO 計算：
1. 把 sample 切 N 份（建議 N=16）
2. 從 N 中選 N/2 為 train（C(N, N/2) 個組合）
3. 每個組合：train 上找最佳策略，test 上看排名
4. PBO = best-on-train 在 test 中是否 > median 的概率

PBO < 0.5 = 模型未過擬合主導。

## 5. CV 結果評估判準

- **Per-fold variance 比 mean 重要**：5 fold metric std / mean > 0.5 → 不穩定，不上線
- IS vs OOS gap：< 30% 健康；30-50% warning；> 50% = 過擬合或 leakage（用 `feature-engineering-protocol` RCA）

## 6. 工作流（10 步）

1. 資料 sort by ts → 2. 每 sample 補 label end_ts 列 → 3. CV 方法選擇（§3）→ 4. N folds 設計（5-10）→ 5. Window 設計（train 90d / test 30d / embargo 1d）→ 6. Purge 邏輯（train_label_end < test_start）→ 7. Per-fold metrics → 8. Cross-fold consistency（mean ± std）→ 9. IS vs OOS gap → 10. CSCV / PBO（K ≥ 10 model variants 時做）。

## 穩定 CV rule（不會 drift）

時序資料禁用 `KFold`（會 shuffle）；training filter 必含 'live' + 'live_demo'（不混 paper）；TimescaleDB hypertable 支援快速 time-range query for split；embargo size 由 label horizon + autocorrelation 動態決定（不寫死數字）。Label count / row 量必跑 SQL 取真值。

## Cross-Skill 互引（避免重述）

- **C1.b QC 視角**（PSR / DSR / Bonferroni / PBO 判準）走 `walk-forward-validation-protocol`；本 skill = MIT 視角 ML 訓練 CV 設計
- **C1.c feature 設計 + leakage**：feature-side 6 leakage 類型走 `feature-engineering-protocol`，本 skill 補 split-side leakage（purge / embargo）
- **pipeline 成熟度評級**：CV 設計通過 ≠ pipeline live；走 `ml-pipeline-maturity-audit`

## 反模式（見即 Reject）

- `KFold`（time series 禁用）；訓練前 shuffle 時序資料
- `TimeSeriesSplit(gap=0)` 用在 label 含 H 期 horizon 場景
- 沒 purge train 中 label window 重疊；IS 與 OOS sample 重疊（無 embargo）
- 5 fold metric 全用 mean 不看 std
- IS 80% / OOS 60% 不查 leakage
- N=2 fold 還宣稱「驗證過」
- Anchored expanding 用於 regime 快速切換的 crypto（見 §3 推薦）

## 輸出格式

```markdown
# MIT Time Series CV Audit — <model_name> · <date>

## CV 設計
- 方法 / N folds / train_window / test_window / embargo / purge logic

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

MIT returns an immutable `role_fragment_v1` with `payload_kind=finding_fragment_v1` for the task closure; no automatic report or memory append.
```
