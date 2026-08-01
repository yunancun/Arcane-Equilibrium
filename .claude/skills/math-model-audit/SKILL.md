---
name: math-model-audit
description: QC agent 純審查不寫碼：策略數學體檢、sizing/risk metric 驗證、alpha 研究方法論審查、edge 估計可疑、或新方法提案需核對 operator 已拒黑名單時讀（quant 三段鏈中段）。
allowed-tools: Read, Grep, Glob, WebSearch
---

# Math Model Audit（量化數學審計）

> Authority typed matrix 正本見 `16-root-principles-checklist` 頭部（`.codex/agent_registry_v1.json` 定義）：只在同類內比較，跨類標 DRIFT/CONFLICT，runtime 不得合法化 policy denial；即時內容依 authority class 與 fresh evidence 取得，本 skill 不寫死。
> 以內建知識為底：Kelly / VaR / CVaR 公式、t-test / 多重比較 / cluster-SE 統計通識不在本檔重述；本檔只列本專案的偏離（黑名單、SSOT 衝突規則、×365 等）、教訓與 SSOT 指針。

> **S1 風控數字 SSOT**：position size / VaR / drawdown threshold 等所有風控數字以 `settings/risk_control_rules/risk_config_<env>.toml` 為 SSOT；config 不合理 → push back operator，**不信 memory 或 skill 內寫死值**。

> **S6 P0/P1/P2 cross-ref**：三層風控定義見 `srv/docs/decisions/EX-01_..._V2.md` §2.1-§2.3；本 skill 引用屬語意重述。

## 何時觸發

- QC 收到「策略數學體檢」「VaR/CVaR/Kelly 驗證」「白皮書草稿審查」「Alpha 研究方法論」
- 新策略 / 新 sizing / 新 risk metric 上線前
- 既有策略「edge 估計可疑」「樣本分佈異常」排查

## ★ 黑名單：絕不推薦（Operator 已拒絕）

> **本節為 operator 已拒絕方法黑名單唯一正本**（`QC.md` / `quant-strategy-design` 指向此處，不另行重述）。

下列方法**禁止**作為新方案出現在報告 / 建議 / 白皮書中。若 K-Dense-AI 等通用科學 skill 建議了，QC 必須在報告中明確 RETRACT：

| 方法 | 為何拒絕 | 替代方向 |
|---|---|---|
| **HMM 政體偵測**（Hidden Markov） | 過度擬合金融數據，狀態定義主觀，live 表現崩 | 用 ATR / volatility regime 等可解釋 metric |
| **GARCH 家族** | 假設過強（normality / stationarity），crypto 已知違反 | 用 realized vol + bootstrap |
| **VPIN**（Volume-Synchronized PIN） | 學術 toy，crypto VPIN 與 toxic flow 關係未驗 | 用 order book imbalance + funding rate |
| **波動率均值回歸**（單獨） | 在 trending crypto 市場長期失效 | 配合 regime gate / breakout 確認 |
| **獨立 Donchian / 波動率突破** | rolling-window look-ahead bias（current bar 含於 max）→ 必 mean-revert（見 memory `feedback_indicator_lookahead_bias.md`） | 必並列 leak-free shift(1) 對比；信號 + 確認 |

任何方法觸碰本黑名單 = 報告開頭明寫「拒絕，因為 ...」+ 給替代。

## 標準審計維度（5 大；統計通識靠內建知識，下列為專案判準）

### 1. 樣本與基準
- [ ] 樣本量 N 充分（單策略 ≥ 200 trades 或 ≥ 30d，依較嚴）；無倖存者偏差（不剔除已下市 symbol）
- [ ] IS/OOS 切分明確；baseline 合理（buy-hold / random / 簡單 MA cross），不只比 0
- [ ] **Engine_mode 隔離**：edge 估計用 demo 不混 paper（memory `feedback_demo_over_paper_for_edge.md`）

### 2. 統計顯著性
- [ ] t-stat（正確 ddof + df-aware t_crit）；sweep ≥ 3 參數必多重比較校正
- [ ] 觀察非獨立必 cluster-SE（按 symbol 或 day）；effect size 與信賴區間並列，不只看 p

### 3. Look-ahead bias 偵測
- [ ] `rolling(N).max()` / `.min()` **含 current bar** → bias 必 RETRACT；補 `shift(1)` leak-free 版對比
- [ ] z-score / normalization 用全期 mean+std（用了未來資訊）→ 改 expanding window
- [ ] feature 計算用了 target window 內資料 = BUG（entry 後 horizon label 本身 OK）
- [ ] CV 切分尊重時序（TimeSeriesSplit，不是 KFold）

### 4. Sizing 與風控數學
- [ ] Kelly 必 fractional（full Kelly = Reject）；公式與估參靠內建知識
- [ ] VaR：crypto 用 historical（fat tail），95% / 99% 雙列；CVaR / ES 新策略上 live 前必算
- [ ] **Position sizing**：以 RiskConfig `[limits].per_trade_risk_pct`（fraction-domain，實值必讀 TOML）為 SSOT；memory `feedback_position_sizing.md` 寫的「3% risk / trade · 25 symbols」是 operator 設計意圖**但 config 為唯一 runtime 真值**，衝突信 config + push back operator（per S1 systemic）
- [ ] Drawdown bound vs DD-tolerance 對齊；新 symbol 加入時計 ρ（原則 16 組合曝險）

### 5. Live 適用性
- [ ] Demo / Paper 結果不等同 Live（slippage / fee / queue position 降級評估）
- [ ] cost_edge_ratio < 0.5（指針：CONTEXT.md「Cost Gate」條，該處寫 `< 0.8` 與本判準不一致，待 operator 裁；勿與 TOML `[cost_edge]` `trigger_threshold=-0.5` 混淆，語義不同）；fee model 真實（maker rebate vs taker；funding；borrow cost）

## 工作流（6 步）

1. **載入 spec** — 讀策略 / 模型 / 公式定義；對照 CLAUDE.md memory（`project_phase5_promotion_edge_crisis.md` / `project_edge_data_isolation.md` 等）
2. **黑名單體檢** — 任何黑名單方法出現 → RETRACT
3. **5 維度逐項** — 表格化 ✅/⚠️/❌ + 證據
4. **數字復算** — 對 1-2 個關鍵指標重算（grand_mean / shrunk_bps / Sharpe / VaR），與報告對照
5. **對抗性反問** — 「樣本量翻倍 effect 變強還弱？」「換 OOS 還對嗎？」「fee + 1bps 結論還成立嗎？」
6. **判定** — Approve / Conditional（待 N 條件）/ Reject + 替代方案

## 穩定數學原則（不會 drift）

edge_estimator shrinkage prior 必合理（James-Stein 或 Bayesian shrinkage 而非 ad-hoc）；cost_gate 設計需 strategy::symbol cell-level 統計顯著；新策略 audit 必含 demo OOS gross > 0 證據（不是 in-sample）。

## Cross-Skill 互引（避免重述）

- **C1.j 設計 vs 審計視角**：本 skill = **審計**（黑名單 / 對抗反問 / 數字復算 / 樣本診斷）；**設計**走 `quant-strategy-design` + `portfolio-construction-protocol`
- **C1.b PSR / DSR / multiple testing 細節**：走 `walk-forward-validation-protocol`
- **觸發順序**：`quant-strategy-design`（提案）→ 本 skill（數學審計）→ `walk-forward-validation-protocol`（驗證），遞進不可顛倒

## 反模式（見即 Reject）

- 黑名單方法（HMM / GARCH / VPIN / ...）
- p < 0.05 但 N < 30；look-ahead bias 未排查（特別是 rolling max/min）
- Kelly full（不 fractional）
- Sharpe 算 daily 但年化用 ×252（crypto 是 24/7 應 ×365；**本條為 ×365 年化規則唯一正本**，`walk-forward-validation-protocol` 指向此處）
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
