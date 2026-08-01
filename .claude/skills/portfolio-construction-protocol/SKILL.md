---
name: portfolio-construction-protocol
description: QC agent 主用：多策略資金分配、sizing 設計、組合級風險評估、drawdown 降倉決策、live PnL 偏離 backtest 歸因時讀；新策略/新 symbol 加入前必過。
allowed-tools: Read, Grep, Glob, WebSearch
---

# Portfolio Construction Protocol（組合構建手冊）

> Authority typed matrix 正本見 `16-root-principles-checklist` 頭部（`.codex/agent_registry_v1.json` 定義）：只在同類內比較，跨類標 DRIFT/CONFLICT，runtime 不得合法化 policy denial；即時內容依 authority class 與 fresh evidence 取得，本 skill 不寫死。
> 以內建知識為底：Kelly / risk parity / PCA / factor model / VaR / CVaR / Kupiec / Christoffersen / EVT 公式與機制不在本檔重述；本檔只列本專案的判準、配置 SSOT 與教訓。

> **S6 P0/P1/P2 cross-ref**：三層風控定義見 `srv/docs/decisions/EX-01_..._V2.md` §2.1-§2.3；本 skill 引用屬語意重述。

## 何時觸發

- QC 收到「多策略並行如何分配資金」「Kelly sizing 設計」「組合 VaR 計算」「Live 階段為何 PnL 偏離 backtest」
- 加入新策略 / 新 symbol 前的組合風險評估
- Drawdown 觸發降倉決策；季度 portfolio rebalance

## ★ 核心信念

**單策略 alpha 加總 ≠ 組合 alpha**。相關性 / 風險分配 / 動態調整才是真正的 portfolio。
**Live 表現 ≠ Backtest 表現**：必須有歸因機制找差距源頭。

## 1. Kelly 專案判準

- Full Kelly = Reject（estimation error + crypto fat tail 下 wipe-out 風險）；必 fractional，**crypto-specific 推薦 k = 0.10–0.25**
- 更嚴版：用 bootstrap 估 p 的不確定性縮倉（越不確定倉位越小）
- OpenClaw 應用：operator 偏好 3% risk / trade · 25 symbols（memory `feedback_position_sizing`）≈ quarter Kelly + portfolio-level cap；動態 qty 從 ATR 推（歷史 P0-13 ATR scale；當前狀態查 `TODO.md` / reports）；**runtime 真值以 RiskConfig 為 SSOT**（衝突信 config，見 `math-model-audit` §4）

## 2. Risk Budget 分配 — 不在本 skill 寫死

OpenClaw 當前策略名單 + 每策略 budget 隨 Phase / dormancy / 重評變動。**本 skill 不寫死表格**。

- 實際分配 SSOT：`settings/risk_control_rules/risk_config_<env>.toml` `[per_strategy]` 段；策略激活狀態查 `TODO.md` + runtime config
- **修改流程**（對齊 DOC-01 §4.3 + §5.11，原文為準）：P2 範圍內（不觸 P0/P1 硬上限）→ Agent 自主調整；觸 P0/P1 hard limit → Operator 批准；跨 strategy 分配建議經 QC + PM 審查（**非治理規定的硬流程**）
- **通用配置 framework**（不會 drift）：每策略 budget 以 conviction × edge half-life × downside skew 加權；buffer ≥ 20% 緊急 / new strategy slot；high-correlation cluster (ρ > 0.7) 視為 single factor 集中限制

## 3. 相關性判準（OpenClaw 25 symbol）

- 閾值：ρ < 0.3 低相關可獨立；0.3-0.7 需聯合考慮；**ρ ≥ 0.7 視為一個 factor 集中**
- crypto PCA 通常 PC1 ≈ BTC beta（解 50-70% variance）；OpenClaw 25 symbol 多半 ρ > 0.6 vs BTC
- 「25 symbols 分散」實際 PC1 主導 → 真實 effective N **需實證 PCA**（heuristic 估 ~5-8 但**未 verified**；跑 PCA 取 PC1 explained variance 倒推）
- 設計時要算 effective number of bets，不能假設 N=25 獨立

## 4. 風險度量專案判準

- VaR：**crypto 用歷史法**（normal 假設 JB 必拒），95% / 99% 雙列；CVaR 必算（QC 標準）
- VaR backtest：每 250 day rebench；**Kupiec p < 0.05 = VaR 模型作廢**；Christoffersen 驗違反獨立性
- EVT（GEV / GPD）用於 99.9%+ 極端 quantile；crypto fat tail 特別適用
- **Stress test 場景 list（OpenClaw 建議起點）**：①2020-03-12 BTC -50%/24h ②2021-05-19 BTC -30% 單日 ③2022-05 LUNA + 2022-11 FTX cascade ④2024-08-05 BTC -20%/6h ⑤Custom：BTC ±20%/day + funding extremes ±0.5%。每場景算組合 PnL + drawdown + liquidation 風險
- ⚠️ **執行需求**：stress test 需歷史 OHLCV（25 symbol × ≥1m × 對應日期窗）+ funding snapshot；QC 工具（Read/Grep/WebSearch）不直接生 backtest，須走 `helper_scripts/research/` 或協調 E1 跑。盲跑就 cite「stress test pass」= 違反對抗性驗證原則
- Risk decomposition：Marginal / Component VaR 拆每策略貢獻（公式靠內建知識）

## 5-6. Drawdown Control 治理映射 + Live 績效歸因（外移）

治理映射（SM-04 6 states / 跨級恢復禁止 / 觀察窗口，threshold 只留 TOML key、值以 runtime TOML 為準）與 Live 歸因細節：見 `references/governance-extract.md`，需要時讀。
QC 審計判準速記：threshold 數字每次 audit 必 grep `risk_config_<env>.toml` `[cascade]` 重驗；恢復必須渐进（禁跨級回 NORMAL）；realized vs expected edge gap 無對比 = silent decay 無感。

## 7. 工作流（10 步 portfolio review）

1. 當前 risk budget（SSOT §2）→ 2. 相關性矩陣（25 symbol，含 effective N）→ 3. PCA / factor model（PC1 是否還是 BTC beta）→ 4. VaR + CVaR（歷史法 95/99）+ Kupiec backtest → 5. EVT 99.9% quantile → 6. Stress test 5 場景 → 7. Risk decomposition（每策略 component VaR）→ 8. Drawdown 階梯狀態 → 9. Performance attribution（24h / 7d / 30d 拆解）→ 10. Realized vs expected edge gap（cell-level 警報）。

## 穩定 schema rule（不會 drift）

edge_estimator JSON = `strategy::symbol` top-level key；`engine_mode IN ('live','live_demo')` filter 必含兩者；CognitiveModulator confidence_floor 是 OpenClaw 內建 drawdown 動態降倉機制（架構級不變）。

## Cross-Skill 互引（避免重述）

- **C1.i 執行成本 / fee**：逐筆 fee 計算 + maker rebate / PostOnly mechanics 引 `crypto-microstructure-knowledge`
- **C1.j VaR / CVaR / Kelly**：本 skill 為**設計視角**；**驗證視角**（黑名單 / 對抗反問 / Sizing sanity check）引 `math-model-audit`
- **C1.b Walk-forward / DSR / PSR**：策略 alpha 顯著性走 `walk-forward-validation-protocol`

## 反模式（見即 Reject）

- Full Kelly（無 fractional）
- 假設 25 symbols 全獨立（PC1 = BTC beta 主導）
- VaR 無 backtest（Kupiec / Christoffersen）；normal 分布假設算 VaR（crypto JB 拒 normality）
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
ρ matrix median / PC1 explained var / Effective N

## VaR / CVaR
VaR 95% / 99%、CVaR 95%（bps/day）、Kupiec p (target > 0.05)

## EVT
99.9% quantile: V bps

## Stress test
| 場景 | PnL | DD |

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
