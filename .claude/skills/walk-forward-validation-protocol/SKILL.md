---
name: walk-forward-validation-protocol
description: 量化策略「驗證 / 回測」操作手冊 — Walk-forward、Deflated Sharpe、PSR、PBO、CSCV、multiple testing 修正、樣本量、資料品質統計診斷、參數穩健性。QC agent 主用，與 quant-strategy-design 互補（design vs validation）。
allowed-tools: Read, Grep, Glob, Bash, WebSearch
---

# Walk-Forward Validation Protocol（驗證 / 回測手冊）

> **優先序**：runtime RiskConfig TOML > Rust schema > CLAUDE.md > 治理 .md > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

> **S1 風控數字 SSOT**：策略 sizing / drawdown / position cap 等所有風控數字以 `settings/risk_control_rules/risk_config_<env>.toml` 為 SSOT；config 不合理 → push back operator，**不信 memory 或 skill 內寫死值**。

## 何時觸發

- QC 收到「策略上線前驗證」「Sharpe 顯著嗎」「參數 sweep 結果評審」「OOS 效能判斷」
- 任何引用 in-sample 表現的策略提案（要立即要求 OOS 驗證）
- 對 P0-3 / Phase 5 重評等需要 demo 21d gross > 0 判斷的場景

## ★ 黃金法則

**In-sample 表現是故事，OOS 表現才是證據**。
**單一 Sharpe 是空話**：必須 deflate / probabilistic 化才有資訊量。

## 1. Walk-Forward 設計

### 1.1 Rolling vs Anchored
- **Rolling window**：固定訓練窗（如 90d），滑動。適合 regime 切換頻繁、半衰期短
- **Anchored expanding**：訓練窗從 t0 累積。適合長期穩定 alpha
- **OpenClaw 預設**：Rolling 90d train + 30d test，crypto regime 切換快不適合 anchored

### 1.2 Purged + Embargo（Lopez de Prado）
ML 訓練 + 信號預測時必加：
- **Purge**：train 樣本中刪除與 test 重疊期的 label 影響
- **Embargo**：train end 後跳過 N 天再開 test，避免 cross-contamination
- OpenClaw `feedback_indicator_lookahead_bias`：rolling-max 含 current bar 屬同類問題

### 1.3 樣本量
| Test 期 | 最少 trade 數 | 對應 OpenClaw 場景 |
|---|---|---|
| 1m timeframe / 5 strat | ≥ 200 trades | demo ~21d 累積 |
| 5m timeframe | ≥ 100 trades | demo ~14d |
| 1h timeframe | ≥ 50 trades | demo ~30d |

樣本不足 → t-test power < 0.5，結論無意義。

## 2. Sharpe 系列進階指標（單 Sharpe 不夠）

### 2.1 Probabilistic Sharpe Ratio (PSR) — Bailey & Lopez de Prado (2012)
給定樣本 Sharpe `SR_obs` 跟期望 benchmark `SR*`（通常 = 0），計算「真 Sharpe > SR* 的機率」：
```
PSR(SR*) = Φ( (SR_obs - SR*) · sqrt(N-1) / sqrt(1 - γ3·SR_obs + (γ4-1)/4·SR_obs²) )
```
- γ3 = skew，γ4 = kurtosis
- crypto returns 高峰厚尾 → kurt 高 → PSR 比 normal 假設低
- **判讀**：PSR(0) > 0.95 才算「Sharpe 顯著大於 0」

### 2.2 Deflated Sharpe Ratio (DSR) — Multiple Testing 修正
若 sweep 過 K 個參數組合，「最高 Sharpe」要 deflate：
```
SR_max_expected = sqrt(Var(SR)) · ( (1-γ)·Φ⁻¹(1-1/K) + γ·Φ⁻¹(1-1/(K·e)) )
γ = Euler-Mascheroni ≈ 0.5772
DSR = PSR(SR_max_expected)
```
- K=100 sweep + naive Sharpe 1.5 可能 deflate 後 < 0
- **OpenClaw P1-11 BB sweep 必跑 DSR**

### 2.3 進階績效指標
| 指標 | 公式 | 何時用 |
|---|---|---|
| **Sortino** | `mean / std_downside` | 上行波動不算風險（asymmetric） |
| **Calmar** | `annual_return / max_drawdown` | 對 drawdown 敏感的場景 |
| **Omega(τ)** | `E[max(R-τ, 0)] / E[max(τ-R, 0)]` | 全分布資訊（非僅二階） |
| **MAR ratio** | `CAGR / max_DD` | 跟 Calmar 同類 |
| **Drawdown duration** | 從峰到復元天數 | 心理 / 資金成本評估 |

## 3. Multiple Testing 修正（必做）

任何 sweep ≥ 3 參數 = 多重假設檢驗。**不修正 = false positive 必爆**。

| 方法 | 適用 | 嚴格度 |
|---|---|---|
| **Bonferroni** | 獨立或弱相關 hypothesis | 最嚴 — α / K |
| **Holm-Bonferroni** | 同上但 step-down | 比 Bonferroni 弱一點 |
| **Benjamini-Hochberg (FDR)** | 大規模 testing 容忍 false discovery | 寬鬆 |
| **White's Reality Check** | 策略選擇場景，含 bootstrap | 量化 best-of-K bias |
| **Romano-Wolf** | step-down + bootstrap | 較精緻 |

OpenClaw 預設：sweep ≥ 5 用 Bonferroni；sweep ≥ 20 用 BH（FDR=0.10）。

## 4. PBO / CSCV — Probability of Backtest Overfitting

Lopez de Prado et al. (2014, 2017)。

**核心**：把樣本切 N 半，所有 K 個策略各跑「半樣本最佳 vs 另半樣本實測」，看 best-on-A 在 B 是否仍 top-50%。
- PBO < 0.5 = 過擬合不嚴重
- PBO > 0.5 = 過擬合主導，棄

**CSCV（Combinatorially Symmetric CV）** 是 PBO 的具體計算法。建議用 `pbo` Python 套件或自寫。

## 5. 資料品質統計診斷（時序分析前置）

任何時序回測前必跑：

| Test | 對象 | 閾值 |
|---|---|---|
| **ADF**（Augmented Dickey-Fuller） | stationarity | p < 0.05 = stationary |
| **KPSS** | stationarity（反向 null） | p > 0.05 = stationary |
| **Phillips-Perron** | stationarity（HAC robust） | 同 ADF |
| **Engle-Granger** | cointegration（pairs trading）| p < 0.05 = cointegrated |
| **Johansen** | multi-asset cointegration | trace stat |
| **Ljung-Box** | autocorrelation | p < 0.05 = autocorr 存在 |
| **Durbin-Watson** | residual autocorrelation | DW ≈ 2 = 無 |
| **Breusch-Pagan** / **White** | heteroscedasticity | p < 0.05 = 異質變異數 |
| **Jarque-Bera** | normality | p < 0.05 = 非正態（crypto 必非）|
| **Anderson-Darling** | distribution fit | 比 KS 對 tail 敏感 |

**OpenClaw crypto 已知**：
- ADF 通常拒 unit root（returns 平穩）
- JB 必拒 normality（kurt > 3 fat tail）→ 任何 normal 假設模型作廢
- ARCH effect（vol clustering）顯著 → naive variance 估計低估

## 6. 參數穩健性

### 6.1 Plateau vs Cliff
策略 P&L 對參數作 heat map：
- **Plateau**：相鄰參數組表現相似 → 穩健
- **Cliff**：小擾動 collapse → 過擬合

OpenClaw 反例：BB squeeze_bw=0.03 100% 觸發、expansion_bw=0.04 永不達 → 不是 plateau 是 binary（CLAUDE.md §三 P1-11 F1）

### 6.2 Bootstrap 置信區間
重抽樣 1000 次計算指標分布：
- IID bootstrap：returns 獨立場景（crypto 多半不對）
- **Block bootstrap**（Politis-Romano）：保留 autocorrelation 結構，crypto 必用
- 給 Sharpe / max_DD 95% CI，不只 point estimate

### 6.3 In-sample vs OOS Sharpe 退化曲線
畫 IS Sharpe vs OOS Sharpe 散點圖。
- 健康策略：OOS ≈ 0.5–0.8 × IS
- 退化嚴重：OOS < 0.3 × IS = 過擬合警報

## 7. 工作流（驗證 SOP，10 步）

1. **資料品質 5 test**（ADF + KPSS + Ljung-Box + JB + ARCH effect）→ 看是否有 unit root / autocorr / heteroscedasticity
2. **In-sample backtest**（leak-free，shift(1) 強制）
3. **Walk-forward 設計**（Rolling 90/30 default，含 purge + embargo）
4. **參數 sweep**（如有）+ 記錄 K
5. **Multiple testing 修正**（Bonferroni 若 K ≥ 5）
6. **DSR 計算**（給 deflate 後 Sharpe）
7. **PSR(0)** ≥ 0.95 確認
8. **PBO / CSCV**（K ≥ 10 時）
9. **Bootstrap CI**（block bootstrap 1000 次，給 Sharpe / max_DD CI）
10. **Plateau analysis**（heat map，確認非 cliff）

任一步 fail = pause + 修。

## OpenClaw 特定核心

- **Engine_mode 隔離**：edge 計算用 demo + live_demo，不混 paper（memory `feedback_demo_over_paper_for_edge`）
- **demo 21d gross > 0** 是 Phase 5 reframed 的 P0-3 重評閾值（CLAUDE.md §三）
- **bb_breakout F3 RETRACT**：Donchian 含 current bar = measurement bias，必並列 shift(1)
- **edge_estimator JSON**：strategy::symbol top-level，不是 `cells{}` nested
- **engine_mode IN ('live', 'live_demo')**：filter 必含兩者
- **OpenClaw 1m timeframe 樣本**：5 strat × 25 symbols × 21d ≈ 充足，但 1m noise 高 → 結論寬 CI
- **outcome_backfiller**：歷史曾因 `timeframe '1' vs '1m'` 字串不一致 + `engine_mode INSERT` 漏接導致 `outcome_*=NULL`，已 fixed（具體 commit + row 數參見 `git log --oneline --all --grep=outcome_backfiller` 動態查；本檔不寫死數字以免漂移）

## 反模式（見即 Reject）

- 只給 Sharpe 不給 PSR / DSR
- Sweep K=100 但無 multiple testing 修正
- 用 KFold 而非 TimeSeriesSplit
- IID bootstrap 而非 block bootstrap
- 「OOS Sharpe = 0.95 × IS Sharpe」(數字太巧 = 可能 leakage)
- ADF / JB 都沒跑就上模型
- 樣本 N < 30 但稱 p < 0.05 顯著
- Sharpe 算 daily 但年化 ×252（crypto 是 24/7 ×365）
- in-sample 報 max_DD = -5%（多半是 selection bias）

## 輸出格式

```markdown
# QC 驗證報告 — <strategy> · <date>

判定：Pass / Conditional（待 N 條件）/ Fail

## 資料品質 5 test
| Test | p | 結論 |
| ADF | | |
| KPSS | | |
| Ljung-Box | | |
| JB | | |
| ARCH | | |

## Sharpe 系列
- Naive SR: X
- PSR(0): Y (target ≥ 0.95)
- DSR: Z (含 K=N deflate)
- Sortino / Calmar: ...
- Drawdown depth × duration: ...

## Walk-forward 設計
Rolling W_train / W_test，Purge=N，Embargo=M

## Multiple testing 修正
方法 / α / 通過數 / 拒絕數

## PBO（如 K ≥ 10）
PBO = X

## Bootstrap CI（block, 1000）
Sharpe 95% CI: [a, b]
max_DD 95% CI: [c, d]

## Plateau 分析
（描述 heat map / cliff 與否）

## OpenClaw 適配
- engine_mode 隔離 ...
- demo 21d gross 達標 ...

## 條件 / 拒絕理由
1. <具體 + 修正路徑>
```
