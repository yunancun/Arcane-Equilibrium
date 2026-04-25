---
name: math-model-audit
description: 策略數學基礎審計、VaR / CVaR / Kelly / position sizing 驗證、Alpha 研究方法論審查；含 Operator 已拒絕方法黑名單。QC agent 純審查，不寫代碼。
allowed-tools: Read, Grep, Glob, WebSearch
---

# Math Model Audit（量化數學審計）

> **優先序**：runtime RiskConfig TOML > Rust schema > CLAUDE.md > 治理 .md > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

> **S1 風控數字 SSOT**：position size / VaR / drawdown threshold 等所有風控數字以 `settings/risk_control_rules/risk_config_<env>.toml` 為 SSOT；config 不合理 → push back operator，**不信 memory 或 skill 內寫死值**。

> **S6 P0/P1/P2 cross-ref**：三層風控定義見 `srv/docs/decisions/EX-01_..._V2.md` §2.1-§2.3；本 skill 引用屬語意重述。

## 何時觸發

- QC 收到「策略數學體檢」「VaR/CVaR/Kelly 驗證」「白皮書草稿審查」「Alpha 研究方法論」
- 新策略 / 新 sizing / 新 risk metric 上線前
- 既有策略「edge 估計可疑」「樣本分佈異常」排查

## ★ 黑名單：絕不推薦（Operator 已拒絕）

下列方法**禁止**作為新方案出現在報告 / 建議 / 白皮書中。若 K-Dense-AI 等通用科學 skill 建議了，QC 必須在報告中明確 RETRACT：

| 方法 | 為何拒絕 | 替代方向 |
|---|---|---|
| **HMM 政體偵測**（Hidden Markov） | 過度擬合金融數據，狀態定義主觀，live 表現崩 | 用 ATR / volatility regime 等可解釋 metric |
| **GARCH 家族** | 假設過強（normality / stationarity），crypto 已知違反 | 用 realized vol + bootstrap |
| **VPIN**（Volume-Synchronized PIN） | 學術 toy，crypto VPIN 與 toxic flow 關係未驗 | 用 order book imbalance + funding rate |
| **波動率均值回歸**（單獨） | 在 trending crypto 市場長期失效 | 配合 regime gate / breakout 確認 |
| **獨立 Donchian / 波動率突破** | rolling-window look-ahead bias（current bar 含於 max）→ 必 mean-revert（見 memory `feedback_indicator_lookahead_bias.md`） | 必並列 leak-free shift(1) 對比；信號 + 確認 |

任何方法觸碰本黑名單 = 報告開頭明寫「拒絕，因為 ...」+ 給替代。

## 標準審計維度（5 大）

### 1. 樣本與基準
- [ ] 樣本量 N 充分（單策略 ≥ 200 trades 或 ≥ 30d，依較嚴）
- [ ] 樣本選擇無倖存者偏差（不剔除已下市 symbol）
- [ ] In-sample / Out-of-sample 切分明確（70/30 或 walk-forward）
- [ ] 基準（baseline）合理（buy-hold / random / 簡單 MA cross），不只比 0
- [ ] **Engine_mode 隔離**：edge 估計用 demo 不混 paper（CLAUDE.md memory `feedback_demo_over_paper_for_edge.md`）

### 2. 統計顯著性
- [ ] t-stat / p-value 計算（含正確 ddof + df-aware t_crit）
- [ ] 多重比較校正（Bonferroni / FDR）若 sweep ≥ 3 參數
- [ ] cluster-SE（按 symbol 或 day cluster）若觀察非獨立
- [ ] effect size 與 p-value 並列（不要只看顯著性）
- [ ] 信賴區間（不只 point estimate）

### 3. Look-ahead bias 偵測

逐項檢查：
- [ ] `rolling(N).max()` / `rolling(N).min()` **含 current bar** → bias 必 RETRACT；補 `shift(1)` leak-free 版對比
- [ ] z-score / normalization 用 全期 mean+std（用了未來資訊）→ 改 expanding window
- [ ] target label 計算用了 entry tick 後 X 分鐘但 feature 在 entry tick 已知（OK，是 horizon）vs feature 計算用了 target window 內資料（BUG）
- [ ] cross-validation 切分尊重時序（TimeSeriesSplit，不是 KFold）

### 4. Sizing 與風控數學

- [ ] **Kelly fraction**：full Kelly 過激，用 fractional Kelly（0.25–0.5）；公式 `f* = (bp - q) / b` 正確使用 + 估 b（odds）+ p（win rate）
- [ ] **VaR**：parametric vs historical 標明；crypto 用 historical（fat tail）；信心度 95% / 99% 雙列
- [ ] **CVaR / ES**：tail loss expectation；新策略上 live 前必算
- [ ] **Position sizing**：Operator 偏好 3% risk / trade · 25 symbols（memory `feedback_position_sizing.md`）+ 動態 qty
- [ ] **Drawdown bound**：max DD vs DD-tolerance 對齊
- [ ] **Correlation / portfolio risk**：原則 16 監控關聯曝險，新 symbol 加入時計 ρ

### 5. Live 適用性
- [ ] Demo / Paper 結果不等同 Live（slippage / fee / queue position 真實後降級多少）
- [ ] cost_edge_ratio < 0.5（CLAUDE.md §二 原則 13）
- [ ] PostOnly / TWAP / VWAP 等執行細節 與 sizing 對齊
- [ ] fee model 真實（maker rebate vs taker；funding rate；borrow cost）

## 工作流（6 步）

1. **載入 spec** — 讀策略 / 模型 / 公式定義；對照 CLAUDE.md memory（`project_phase5_promotion_edge_crisis.md` / `project_edge_data_isolation.md` 等）
2. **黑名單體檢** — 任何黑名單方法出現 → RETRACT
3. **5 維度逐項** — 表格化 ✅/⚠️/❌ + 證據
4. **數字復算** — 對 1-2 個關鍵指標重算（grand_mean / shrunk_bps / Sharpe / VaR），與報告對照
5. **對抗性反問** — 「樣本量翻倍 effect 變強還弱？」「換 OOS 還對嗎？」「fee + 1bps 結論還成立嗎？」
6. **判定** — Approve / Conditional（待 N 條件）/ Reject + 替代方案

## OpenClaw 特定核心

- **edge_estimator**：每 strategy::symbol 的 grand_mean / shrunk_bps，shrinkage prior 必合理（James-Stein 或 Bayesian shrinkage 而非 ad-hoc）
- **cost_gate**：promotion 邊界 grand_mean > −50 bps 且 ≥2 策略 shrunk_bps > 0（CLAUDE.md §三 LEARNING-PIPELINE-DORMANT-1）
- **bb_breakout / squeeze 信號**：1m 尺度 bandwidth match（F1 確認過尺度錯配）
- **PostOnly fee 降幅驗證**：≥1w demo 數據 + maker fill rate
- **Phase 5 reframed**：所有活躍策略 gross edge 為負，新策略上線前必先過 demo 21d gross > 0

## 反模式（見即 Reject）

- 黑名單方法（HMM / GARCH / VPIN / ...）
- p < 0.05 但 N < 30
- look-ahead bias 未排查（特別是 rolling max/min）
- Kelly full（不 fractional）
- Sharpe 算 daily 但年化用 ×252（crypto 是 24/7 應 ×365）
- correlation matrix 未列就推薦多策略並行
- 「demo 表現好」當 live edge 證據（demo / paper / live 隔離原則）
- 「PnL 為正」但 edge_per_trade 為負（過度交易補虧損）

## 輸出格式

```markdown
# QC 數學審計 — <strategy / model> · <date>

範圍：<files / 公式 / 樣本範圍>
判定：Approve / Conditional / Reject

## 黑名單檢查
（觸發黑名單列出 + 替代）

## 5 維度
| 維度 | 狀態 | 證據 |
|---|---|---|
| 樣本基準 | ✅/⚠️/❌ | <具體> |
| 統計顯著 | | |
| Look-ahead bias | | |
| Sizing & 風控 | | |
| Live 適用 | | |

## 數字復算
| 指標 | 報告值 | 我復算 | 差異 | 結論 |

## 對抗性反問
1. Q: ... A: ...

## 條件 / 拒絕理由
1. <具體 + 修正路徑>
```
