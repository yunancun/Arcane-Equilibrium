---
name: walk-forward-validation-protocol
description: QC agent 主用：策略上線前驗證、Sharpe/OOS 顯著性判斷、參數 sweep 評審、提案只引 in-sample 表現時讀（quant 三段鏈之末）；ML 訓練 CV 歸 MIT time-series-cv-protocol。
allowed-tools: Read, Grep, Glob, WebSearch
---

# Walk-Forward Validation Protocol（驗證 / 回測手冊）

> Authority typed matrix 正本見 `16-root-principles-checklist` 頭部（`.codex/agent_registry_v1.json` 定義）：只在同類內比較，跨類標 DRIFT/CONFLICT，runtime 不得合法化 policy denial；即時內容依 authority class 與 fresh evidence 取得，本 skill 不寫死。
> 以內建知識為底：rolling vs anchored 概念、PSR/DSR/Sortino/Calmar/Omega 公式、multiple testing 方法（Bonferroni/Holm/BH/White/Romano-Wolf）、平穩性/自相關/正態性統計檢定、bootstrap、plateau vs cliff 等通識不在本檔重述；本檔只列本專案的判準、教訓與 SSOT 指針。
> 主用者 QC 無 Bash：runtime 取數（psql / trade count / sweep log 等）標註需 MIT/E4 協查，報告列出所需查詢。

> **S1 風控數字 SSOT**：策略 sizing / drawdown / position cap 等所有風控數字以 `settings/risk_control_rules/risk_config_<env>.toml` 為 SSOT；config 不合理 → push back operator，**不信 memory 或 skill 內寫死值**。

> **C1.b cross-skill 邊界**：Purge / Embargo / CSCV 機制細節唯一正本在 `time-series-cv-protocol`（MIT），本 skill 只留 QC 判準。**同時觸發時職責分**：QC 主負策略 alpha 顯著性（PSR / DSR / 統計檢定 / 多重比較），MIT 主負 ML 模型訓練 CV 設計。

## 何時觸發

- QC 收到「策略上線前驗證」「Sharpe 顯著嗎」「參數 sweep 結果評審」「OOS 效能判斷」
- 任何引用 in-sample 表現的策略提案（要立即要求 OOS 驗證）
- 需要 demo 21d gross > 0 判斷的場景

## ★ 黃金法則

**In-sample 表現是故事，OOS 表現才是證據**。**單一 Sharpe 是空話**：必須 deflate / probabilistic 化才有資訊量。

## 1. Walk-Forward 專案判準

- **OpenClaw 建議起點（非治理硬規範）**：Rolling 90d train + 30d test；crypto regime 切換快通常不適合 anchored。具體 window 依策略半衰期 + 樣本量動態調整，新策略提案可由 QC 提替代並說明理由。
- ML 訓練 + 信號預測場景未加 purge + embargo = leakage → Reject（機制正本見 `time-series-cv-protocol`）；rolling-max 含 current bar 屬同類問題（`feedback_indicator_lookahead_bias`）。
- 樣本量下限（OpenClaw 場景對照）：1m timeframe ≥ 200 trades（demo ~21d 累積）；5m ≥ 100（~14d）；1h ≥ 50（~30d）。樣本不足 → t-test power < 0.5，結論無意義。

## 2. Sharpe 顯著性判準（QC 硬判準）

- **PSR(0) > 0.95** 才算「Sharpe 顯著大於 0」；crypto returns 高峰厚尾 → PSR 比 normal 假設低，必用含 skew/kurt 修正版
- **Sweep 過 K 個參數組合必跑 DSR**（deflate 後再判：`SR_max_expected = sqrt(Var(SR))·[(1−γ)·Φ⁻¹(1−1/K) + γ·Φ⁻¹(1−1/(K·e))]`，γ≈0.5772，`DSR = PSR(SR_max_expected)`）；K=100 sweep + naive Sharpe 1.5 可能 deflate 後 < 0。**√Var(SR) 縮放不可省**：實作省略此縮放會使 K≥2 時 deflation 門檻遠高於任何合理 per-trade Sharpe → DSR≈0 恆 block（07-24 run0 QC finding，正本 `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-24--full_system_ultracode_audit_run0.decision_view.json`）
- 進階指標（Sortino / Calmar / Omega / MAR / DD duration）按場景選用，公式靠內建知識

## 3. Multiple Testing 修正（必做）

任何 sweep ≥ 3 參數 = 多重假設檢驗，不修正 = false positive 必爆。OpenClaw 建議起點（**非治理硬規範**）：sweep ≥ 5 用 Bonferroni；sweep ≥ 20 用 BH（FDR=0.10）；具體 K 閾值與方法可由 QC 提替代並說明 Type-I/II trade-off。White's Reality Check / Romano-Wolf 需 Python bootstrap——QC 無 Bash → 報告列需求，協調 E1/MIT/E4 跑。

## 4. PBO / CSCV 判準

CSCV 機制細節唯一正本見 `time-series-cv-protocol` §5。QC 判準：PBO < 0.5 = 過擬合不嚴重；PBO > 0.5 = 過擬合主導，棄。執行需 Python；協調 MIT/E4 跑。

## 5. 資料品質前置（OpenClaw crypto 已知）

回測前跑 5 test（ADF + KPSS + Ljung-Box + JB + ARCH effect；檢定原理靠內建知識）。crypto 已知結論：ADF 通常拒 unit root（returns 平穩）；JB 必拒 normality（fat tail）→ **任何 normal 假設模型作廢**；ARCH effect（vol clustering）顯著 → naive variance 估計低估。

## 6. 參數穩健性判準

- Plateau vs Cliff：heat map 相鄰參數組表現相似才穩健。OpenClaw 反例：BB squeeze_bw=0.03 100% 觸發、expansion_bw=0.04 永不達 → 不是 plateau 是 binary（歷史 P1-11 F1；當前狀態查 `TODO.md` / reports）
- Bootstrap CI：crypto returns 有 autocorrelation → **必用 block bootstrap**（IID bootstrap = 反模式）；給 Sharpe / max_DD 95% CI 不只 point estimate
- IS vs OOS 退化：健康 OOS ≈ 0.5–0.8 × IS；OOS < 0.3 × IS = 過擬合警報；OOS ≈ 0.95 × IS 數字太巧 = 可能 leakage

## 7. 工作流（11 步含 step 0 樣本量檢查）

0. **樣本量 N_min 預先檢查**（強制前置，2026-04-25 加）：rule-of-thumb — detect Sharpe > 0 顯著 ≥ 30 trades；Δ=0.5 ≥ 60；Δ=0.2 ≥ 200（power 公式靠內建知識）。OpenClaw 1m 對照：21d demo 通常 ≥ 300 trades 可達 §1 閾值；< 200 trades 先延長累積期，不直接跑 sweep。取數 QC 無 Bash → 協調 MIT/E4。樣本不足 → 報告標 BLOCKED + 樣本量證據後結束，不暫停等待。
1. 資料品質 5 test → 2. In-sample backtest（leak-free，shift(1) 強制）→ 3. Walk-forward 設計（Rolling 90/30 起點，含 purge + embargo）→ 4. 參數 sweep + 記錄 K → 5. Multiple testing 修正 → 6. DSR → 7. PSR(0) ≥ 0.95 → 8. PBO / CSCV（K ≥ 10 時）→ 9. Block bootstrap CI → 10. Plateau analysis。

任一步 fail → 報告標 BLOCKED + 該步證據 + 所需修正後結束，不暫停等待。

## 穩定驗證 rule（不會 drift）

edge 計算只用 demo + live_demo（不混 paper）；`engine_mode IN ('live','live_demo')` filter 必含兩者；rolling stat 必加 `.shift(1)` leak-free；crypto annualization ×365 非 ×252（正本見 `math-model-audit` 反模式）。

## 反模式（見即 Reject）

- 只給 Sharpe 不給 PSR / DSR；Sweep K=100 但無 multiple testing 修正
- 用 KFold 而非 TimeSeriesSplit；IID bootstrap 而非 block bootstrap
- 「OOS Sharpe = 0.95 × IS Sharpe」（數字太巧 = 可能 leakage）
- ADF / JB 都沒跑就上模型；樣本 N < 30 但稱 p < 0.05 顯著
- Sharpe 算 daily 但年化 ×252（×365 規則正本見 `math-model-audit` 反模式）
- in-sample 報 max_DD = -5%（多半是 selection bias）

## 輸出格式

```markdown
# QC 驗證報告 — <strategy> · <date>

判定：Pass / Conditional（待 N 條件）/ Fail

## 資料品質 5 test
| Test | p | 結論 |

## Sharpe 系列
- Naive SR / PSR(0)（target ≥ 0.95）/ DSR（含 K=N deflate）/ Sortino / Calmar / DD depth × duration

## Walk-forward 設計
Rolling W_train / W_test，Purge=N，Embargo=M

## Multiple testing 修正
方法 / α / 通過數 / 拒絕數

## PBO（如 K ≥ 10）
PBO = X

## Bootstrap CI（block）
Sharpe 95% CI: [a, b]；max_DD 95% CI: [c, d]

## Plateau 分析
（heat map / cliff 與否）

## OpenClaw 適配
- engine_mode 隔離 / demo 21d gross 達標

## 條件 / 拒絕理由
1. <具體 + 修正路徑>
```
