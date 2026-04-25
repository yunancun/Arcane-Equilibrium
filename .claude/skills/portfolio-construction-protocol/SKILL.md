---
name: portfolio-construction-protocol
description: 組合構建與資金管理手冊 — Kelly fractional 四層、Risk parity、相關性與因子分析、VaR/CVaR/EVT、Stress test、Risk decomposition、Drawdown control、Live 階段績效歸因。QC agent 主用。
allowed-tools: Read, Grep, Glob, WebSearch
---

# Portfolio Construction Protocol（組合構建手冊）

> **優先序**：runtime RiskConfig TOML > Rust schema > CLAUDE.md > 治理 .md > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

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
- 動態 qty 從 ATR 推（CLAUDE.md §三 P0-13 ATR scale）

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

### 2.3 OpenClaw 5 策略當前 risk budget（**建議起點，非治理硬規範**）

| 策略 | suggested budget | 理由 |
|---|---|---|
| grid_trading | 25% | edge 不明 + fee drag 大 |
| ma_crossover | 20% | R:R 不對稱（CLAUDE.md §三 P1-10）|
| bb_breakout | 15% | dormancy 修復後重新累積 |
| bb_reversion | 15% | 同上 |
| funding_arb | 0% | G-2 結案 negative；**保留 dormant slot 待 R-02 重評**（不刪）|
| **未分配 buffer** | 25% | 緊急 + new strategy slot |

合計 100%。

**修改流程**（對齊 DOC-01 §4.3 + §5.11）：
- **P2 範圍內**（不觸 P0/P1 硬上限）→ Agent 自主調整（DOC-01 §5.11）
- **觸 P0/P1 hard limit** → Operator 批准（DOC-01 §4.3 已定 5 項批准範圍）
- 跨 strategy 分配建議經 QC + PM 審查（quant + project 視角），但**不是治理規定的硬流程**

實際 RiskConfig `[per_strategy]` 段是治理的真實分配位置；本表為 reference，每次調整以 RiskConfig TOML 為準。

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
- 「25 symbols 分散」實際上 PC1 主導 → 真實 effective N ≈ 5-8
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
場景 list（OpenClaw 必須過）：
1. 2020-03-12 BTC -50% / 24h
2. 2021-05-19 LUNA collapse
3. 2022-06 / 11 cascade（LUNA / FTX）
4. 2024-08-05 BTC -20% / 6h
5. Custom：BTC ±20% / day + funding extremes ± 0.5%

每個場景算組合 PnL + drawdown + liquidation 風險。

### 4.6 Risk Decomposition
```
σ_p² = Σ_i Σ_j w_i·w_j·σ_i·σ_j·ρ_ij
component_VaR_i = w_i · ρ_iP · σ_i / σ_p × VaR
```
- Marginal VaR：增加單位 i 倉位對 portfolio VaR 的影響
- Component VaR：i 對 total VaR 的貢獻

## 5. Drawdown Control（對齊 SM-04 + RiskConfig）

**SM-04 是治理 SSOT**（`srv/docs/decisions/SM-04_..._V1.md`）：6 named states + event-driven + observation window；具體 % threshold 讀 RiskConfig `[cascade]`。

### 5.1 SM-04 狀態與 RiskConfig 觸發 mapping

| SM-04 state | 行為約束（見 SM-04 §9） | RiskConfig threshold（base / demo） |
|---|---|---|
| **NORMAL** | 正常裁決 | drawdown < `drawdown_cautious_pct` |
| **CAUTIOUS** | 提高入場門檻 + 下調倉位 + 提高 manual review | drawdown ≥ `drawdown_cautious_pct`（5.0 / 8.0）|
| **REDUCED** | 大比例 downsize + 局部凍結 + 限制訂單類型 | drawdown ≥ `drawdown_reduced_pct`（8.0 / 15.0）|
| **DEFENSIVE** | reduce-only + protective only + 禁新風險 | drawdown ≥ `drawdown_defensive_pct`（12.0 / 20.0）|
| **CIRCUIT_BREAKER** | 停止非保護性推進 + 凍結 live 扩张 | drawdown ≥ `drawdown_circuit_pct`（15.0 / 22.0）|
| **MANUAL_REVIEW** | 人工審批指定範圍 | operator emergency / multi-layer conflict |

具體值以 `settings/risk_control_rules/risk_config_<env>.toml` `[cascade]` 為 SSOT。**不信本表內數字**，每次 audit 必 grep TOML 重驗。

### 5.2 跨級恢復禁止（SM-04 §7.1）

明禁：
- CIRCUIT_BREAKER → NORMAL
- DEFENSIVE → NORMAL
- REDUCED → NORMAL

恢復必須**渐进**：CIRCUIT_BREAKER → DEFENSIVE → REDUCED → CAUTIOUS → NORMAL，且每步須觀察窗口完成。

### 5.3 觀察窗口要求（SM-04 §11）

進入更宽松前必有 observation_window：
- 禁進一步放寬超過當前批准級別
- 提高審計密度
- 提高 incident / near-miss 檢查頻率

結束條件（SM-04 §11.3）：
- 無新增同類異常
- 觸發恢復的根因已不再出現
- 審計鏈、對賬鏈、健康鏈穩定
- Operator 未提出回退

### 5.4 OpenClaw 對應實現

- CognitiveModulator.confidence_floor 動態調整（CLAUDE.md memory `feedback_agent_autonomy`）
- P0/P1 硬邊界（DOC-01 §5.11；P2 範圍 Agent 自主）
- Performance Attribution 拆解（見 §6 Live 階段績效歸因）

## 6. Live 階段績效歸因（a3 整合）

### 6.1 Performance Attribution 拆解
```
Total PnL = Σ_strategy PnL_strat + interaction
PnL_strat = Σ_symbol PnL_sym
PnL_sym = (entry_alpha + exit_alpha + holding_alpha) − (fee + slippage + funding)
```

### 6.2 Realized vs Expected Edge Gap
每 24h 對每 (strategy, symbol) 比對：
- Backtest expected edge per trade
- Live realized edge per trade
- Gap > 50% 的 cell → 警報

OpenClaw 教訓：edge_estimator JSON 結構 + engine_mode 隔離（live vs live_demo 必含）。

### 6.3 Slippage Monitoring
- Expected fill price（mid）vs actual fill price
- Per (symbol, hour, order_type) 分群統計
- 異常時段 / symbol 列為高 slippage cell

### 6.4 Position-level P&L Decomposition
- Entry alpha（從 entry 到第一個 favourable move）
- Exit alpha（exit 是 take profit / stop loss / phys lock）
- Holding alpha（中間部分）
- 對應 OpenClaw `learning.exit_features` table

### 6.5 Rolling Sharpe / Drawdown Duration 動態追蹤
- 30d rolling Sharpe 圖
- Underwater curve（drawdown 持續多久）
- 若 60d Sharpe < 0 → 全策略 review

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

## OpenClaw 特定核心

- **edge_estimator JSON**：strategy::symbol top-level（不是 cells{}）
- **engine_mode IN ('live', 'live_demo')**：filter 必含兩者
- **5 策略 negative gross edge**：當前所有活躍策略 gross 為負（CLAUDE.md §三 Phase 5 reframed），portfolio 暫無 alpha 可分配，主要工作 = 等 demo 21d 重評
- **3% risk / trade · 25 symbols**：operator 既定（memory `feedback_position_sizing`）
- **funding_arb 0% budget**：G-2 結案 negative（memory `project_g2_funding_arb_monitor`）
- **PostOnly fee 改善**：EDGE-P2-3 demo=true，Live 待 G1-05 fix
- **CognitiveModulator confidence_floor**：drawdown 動態降倉的 OpenClaw 內建機制
- **Live 階段監控基建**：edge_estimator_scheduler daemon + cron 6h `passive_wait_healthcheck`（17 check）

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
| 2021-05-19 LUNA | | |
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
