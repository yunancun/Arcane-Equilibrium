---
name: portfolio-construction-protocol
description: 組合構建與資金管理手冊 — Kelly fractional 四層、Risk parity、相關性與因子分析、VaR/CVaR/EVT、Stress test、Risk decomposition、Drawdown control、Live 階段績效歸因。QC agent 主用。
allowed-tools: Read, Grep, Glob, WebSearch
---

# Portfolio Construction Protocol（組合構建手冊）

> 權威序：runtime RiskConfig TOML > Rust schema > srv/TODO.md > 治理文件（SPECIFICATION_REGISTER.md 索引）> 本 skill。衝突按權威序執行並在報告標註，不停下等待。
> 即時狀態（策略名單/閾值/端點/baseline 等）以上述 SSOT 為準，本 skill 不寫死。

> **S6 P0/P1/P2 cross-ref**：三層風控定義見 `srv/docs/decisions/EX-01_..._V2.md` §2.1-§2.3；本 skill 引用屬語意重述。

## 何時觸發

- QC 收到「多策略並行如何分配資金」「Kelly sizing 設計」「組合 VaR 計算」「Live 階段為何 PnL 偏離 backtest」
- 加入新策略 / 新 symbol 前的組合風險評估
- Drawdown 觸發降倉決策
- 季度 portfolio rebalance

## ★ 核心信念

**單策略 alpha 加總 ≠ 組合 alpha**。相關性 / 風險分配 / 動態調整才是真正的 portfolio。
**Live 表現 ≠ Backtest 表現**：必須有歸因機制找差距源頭。

## 1. Kelly Fractional 四層

### 1.1 Full Kelly（不要用）
```
f* = (b·p − q) / b   ， b = win/loss ratio, p = win rate, q = 1−p
```
**警告**：Full Kelly 會 maximize geometric growth 但 drawdown 高到無法承受。在 estimation error 下 + crypto fat tail，Full Kelly 在 5% 機率下 wipe-out。

### 1.2 Fractional Kelly（建議）
```
f_frac = f* × k   ， k ∈ [0.10, 0.50]
```
- **k = 0.25**：標準保守（quant fund 常規）
- **k = 0.10**：crypto-specific 推薦（fat tail buffer）
- 大多 crypto-fund 用 quarter Kelly

### 1.3 Kelly with Estimation Uncertainty（更嚴）
```
f_safe = f_frac × (1 − std(p)·z) / mean(p)
```
- 用 bootstrap 估計 p 的不確定性
- 越不確定，倉位越小

### 1.4 OpenClaw 應用
- Operator 偏好：3% risk / trade · 25 symbols（memory `feedback_position_sizing`）
- 對應約 quarter Kelly + portfolio-level cap
- 動態 qty 從 ATR 推（歷史 P0-13 ATR scale；當前狀態查 `TODO.md` / reports）

## 2. Risk Parity & Risk Budgeting

### 2.1 Risk Parity
每個策略 / asset 對組合波動的貢獻相等：
```
σ_contribution_i = w_i × ∂σ_p / ∂w_i = c   ， 對所有 i 相同
```
- 高波動 asset 自動被分配低 weight
- 不需估 expected return（避 estimation error）

### 2.2 Risk Budgeting（更靈活）
給每個策略指定一個 risk budget，按 budget 分配 weight。
- 高信心策略 → 高 budget
- 新策略 / shadow 階段 → 低 budget

### 2.3 Risk budget 分配 — 不在本 skill 寫死

OpenClaw 當前 5 策略名單 + 每策略 budget 隨 Phase / dormancy / R-02 重評變動。**本 skill 不寫死表格**避免 sub-agent 引過期數字當分配依據。

實際分配 SSOT：`settings/risk_control_rules/risk_config_<env>.toml` `[per_strategy]` 段；策略激活狀態查 `TODO.md` + runtime config。

**修改流程**（對齊 DOC-01 §4.3 + §5.11，原文為準）：
- **P2 範圍內**（不觸 P0/P1 硬上限）→ Agent 自主調整（DOC-01 §5.11）
- **觸 P0/P1 hard limit** → Operator 批准（DOC-01 §4.3 已定的批准範圍）
- 跨 strategy 分配建議經 QC + PM 審查（quant + project 視角），**非治理規定的硬流程**

**通用配置 framework**（不會 drift）：每策略 budget 以 conviction × edge half-life × downside skew 加權；buffer ≥ 20% 緊急 / new strategy slot；high-correlation cluster (ρ > 0.7) 視為 single factor 集中限制。

## 3. 相關性與因子分析

### 3.1 相關性矩陣
- **Pearson** ρ：linear，crypto 多半適用
- **Spearman** ρ：rank-based，極端值 robust
- **Kendall** τ：另一 rank correlation

**閾值**：
- ρ < 0.3：低相關，可獨立計算
- 0.3 ≤ ρ < 0.7：中相關，需聯合考慮
- ρ ≥ 0.7：高相關，視為一個 factor 集中

### 3.2 PCA 因子提取
- 對 25 symbol 報酬做 PCA
- crypto 通常：PC1 ≈ BTC beta（解 50-70% variance）
- PC2 ≈ DeFi / L1 sector
- PC3 ≈ meme / altcoin rotation

### 3.3 Factor Risk Model（Barra-style 簡版）
```
return_i = α_i + β1·F_BTC + β2·F_sector + β3·F_macro + ε_i
```
- 拆解每個 symbol 的 systematic vs idiosyncratic risk
- portfolio risk = β'·Σ_F·β + Σ idio_var

### 3.4 Hedging Ratio
- 多空兩腿配對：`hedge_ratio = β · (notional_long / notional_short)`
- crypto 主要 hedge：BTC perp short

### 3.5 OpenClaw 25 symbol 應用
- 多半高相關（ρ > 0.6 vs BTC）
- 「25 symbols 分散」實際上 PC1 主導 → 真實 effective N **需實證 PCA**（heuristic 估計 ~5-8 但**未 verified**；具體值跑 PCA on 25 symbol returns 取 PC1 explained variance 倒推）
- 設計時要算 effective number of bets，不能假設 N=25 獨立

## 4. 風險度量 / 風控數學深化

### 4.1 VaR
```
VaR(α) = inf{x : P(L ≤ x) ≥ α}
```
**參數法**（normal 假設，crypto 慎用）：`VaR = μ + σ·z_α`
**歷史法**（建議 crypto）：取 returns 排序的 α 分位
**Monte Carlo**（複雜組合）：模擬 M 次取分位

**OpenClaw 預設**：歷史法 95% / 99% 雙列。

### 4.2 CVaR / Expected Shortfall
```
CVaR(α) = E[L | L > VaR(α)]
```
- VaR 之後的 tail 平均
- 比 VaR 對 fat tail 更合理
- 必算（QC 標準）

### 4.3 VaR Backtesting
- **Kupiec POF (Proportion of Failures)**：實際違反率 vs 預期 α
  ```
  LR_uc = -2·ln( (1-α)^(N-x) · α^x / ((1-x/N)^(N-x) · (x/N)^x) ) ~ χ²(1)
  ```
- **Christoffersen 條件覆蓋**：違反獨立性（不 cluster）

每 250 day rebench VaR backtest；Kupiec p < 0.05 = VaR 模型作廢。

### 4.4 EVT（極值理論）
- **Block Maxima**：分塊取最大 → fit GEV
- **POT (Peaks Over Threshold)**：超閾值 fit GPD
- 用於 99.9%+ 極端 quantile 估計
- crypto 特別適用（fat tail）

### 4.5 Stress Testing
場景 list（OpenClaw 建議起點）：
1. 2020-03-12 BTC -50% / 24h
2. 2021-05-19 BTC -30% 單日（中國挖礦禁令 + 槓桿清洗 cascade）
3. 2022-05 LUNA collapse + 2022-11 FTX cascade
4. 2024-08-05 BTC -20% / 6h
5. Custom：BTC ±20% / day + funding extremes ± 0.5%

每個場景算組合 PnL + drawdown + liquidation 風險。

> ⚠️ **執行需求**：5 場景 stress test 需歷史 OHLCV（25 symbol × ≥ 1m × 對應日期窗口）+ funding rate snapshot；sub-agent 工具（Read / Grep / WebSearch）不直接生 backtest，須走 `helper_scripts/research/` 或協調 E1 跑 Python backtest。盲跑就 cite「stress test pass」= 違反對抗性驗證原則。

### 4.6 Risk Decomposition
```
σ_p² = Σ_i Σ_j w_i·w_j·σ_i·σ_j·ρ_ij
component_VaR_i = w_i · ρ_iP · σ_i / σ_p × VaR
```
- Marginal VaR：增加單位 i 倉位對 portfolio VaR 的影響
- Component VaR：i 對 total VaR 的貢獻

## 5-6. Drawdown Control 治理映射 + Live 績效歸因（外移）

治理映射（SM-04 6 states / 跨級恢復禁止 / 觀察窗口，threshold 只留 TOML key、值以 runtime TOML 為準）與 Live 歸因細節（attribution 拆解 / edge gap / slippage / P&L decomposition）：見 `references/governance-extract.md`，需要時讀。
QC 審計判準速記：threshold 數字每次 audit 必 grep `risk_config_<env>.toml` `[cascade]` 重驗；恢復必須渐进（禁跨級回 NORMAL）；realized vs expected edge gap 無對比 = silent decay 無感。

## 7. 工作流（10 步 portfolio review）

1. **5 策略當前 risk budget**（對照 §2.3 表）
2. **相關性矩陣**（25 symbol returns，含 effective N）
3. **PCA / factor model**（PC1 是否還是 BTC beta）
4. **VaR + CVaR**（歷史法 95/99）+ Kupiec backtest
5. **EVT 99.9% 極端 quantile**
6. **Stress test 5 場景**
7. **Risk decomposition**（每策略 component VaR）
8. **Drawdown 階梯狀態**（當前 DD vs trigger 階梯）
9. **Performance attribution**（24h / 7d / 30d 拆解）
10. **Realized vs expected edge gap**（cell-level 警報）

## 穩定 schema rule（不會 drift）

edge_estimator JSON = `strategy::symbol` top-level key；`engine_mode IN ('live','live_demo')` filter 必含兩者；CognitiveModulator confidence_floor 是 OpenClaw 內建 drawdown 動態降倉機制（架構級不變）。

## Cross-Skill 互引（避免重述）

- **C1.i 執行成本 / fee**：本 skill 列 risk budget 與 portfolio 級 fee drag，**逐筆 fee 計算 + maker rebate / PostOnly mechanics 不重述** — 引 `crypto-microstructure-knowledge` §5「Execution Optimization」
- **C1.j VaR / CVaR / Kelly**：本 skill 為 **設計視角**（如何分配、組合層級指標）；**驗證視角**（黑名單 / 對抗反問 / Look-ahead bias 偵測 / Sizing sanity check）引 `math-model-audit`
- **C1.b Walk-forward / DSR / PSR**：策略 alpha 顯著性走 `walk-forward-validation-protocol`；本 skill 不重述 multiple testing 細節

## 反模式（見即 Reject）

- Full Kelly（無 fractional）
- 假設 25 symbols 全獨立（PC1 = BTC beta 主導）
- VaR 無 backtest（Kupiec / Christoffersen）
- normal 分布假設算 VaR（crypto JB 拒 normality）
- Stress test 沒過 LUNA / FTX cascade
- Drawdown 無動態降倉機制
- Live 階段沒績效歸因 → 不知 PnL 偏離 backtest 為何
- realized edge 沒跟 expected 對比 → silent decay 無感
- 「100% 分配」沒 buffer（緊急 + new strategy slot）

## 輸出格式

```markdown
# QC Portfolio Construction 評估 — <date>

## Risk budget
| 策略 | budget % | 理由 |

## 相關性 / Effective N
- ρ matrix（25 symbol） median: X
- PC1 explained var: Y%
- Effective N ≈ Z

## VaR / CVaR
- VaR 95%: X bps / day
- VaR 99%: Y bps / day
- CVaR 95%: Z bps / day
- Kupiec p: W (target > 0.05)

## EVT
99.9% quantile: V bps

## Stress test
| 場景 | PnL | DD |
| 2020-03-12 BTC -50% | | |
| 2021-05-19 BTC -30% | | |
| 2022-05 LUNA | | |
| 2022-11 FTX | | |

## Risk decomposition
| 策略 | weight | component VaR |

## Drawdown 狀態
當前 DD: X% / trigger: Y level

## Performance attribution（如 live data）
| 期間 | total | strategy 拆 | cost |

## Realized vs Expected gap
（cell-level 警報，> 50% gap 列出）

## 結論 + 建議
Approve / Conditional / Reject + 建議 rebalance
```
