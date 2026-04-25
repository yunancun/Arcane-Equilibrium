**EX-05**

Learning Boundary

學習邊界定義

OpenClaw / Bybit AI Agent Trading System

**Version 2.0  —  2026-03-29**

*Classification: Internal — Governance Document*


# 修訂歷史 / Revision History

| **Date** | **Ver** | **Author** | **Changes** |
|---|---|---|---|
| 2026-03-24 | 1.0 | Claude / Operator | Initial learning boundary (suggestion generation only) |
| 2026-03-26 | 1.1 | Claude / Operator | Minor alignment |
| 2026-03-29 | 2.0 | Claude / Operator | Major expansion: Evolution Engine L1–L5, strategy incubation pipeline, cross-strategy transfer learning, regime transition prediction, learning data lifecycle, Analyst autonomy boundaries |


# §1 用途與設計哲學 / Purpose & Design Philosophy

**V1 定位：**學習系統是「建議生成器」——記錄觀察、提取教訓、生成建議供 Operator 審閱。

**V2 升級：**學習系統是「進化引擎」——Analyst Agent 從被動記錄升級為主動進化，可自主孵化新策略、跨策略遷移學習、預測 regime 轉換。但仍嚴格遵守「學習 ≠ 自作主張」（根原則 #7）。

**核心區分：**學習可以自動產生洞察和提案，但不能自動修改 live 配置、放開權限、修改代碼上線。策略孵化流程是學習的最大自主權邊界。


# §2 學習管線 / Learning Pipeline

The learning pipeline is a five-stage funnel. Each stage has distinct data requirements, automation levels, and governance rules.


| **#** | **Stage** | **中文** | **Description** | **Automation** | **API** | **Governance** |
|---|---|---|---|---|---|---|
| 1 | Observation | 觀察 | Raw record of what happened: trade result, market state, system behavior | Fully automatic | PipelineBridge emits on every round-trip (E1/E1a/E1b) | Append-only, immutable |
| 2 | Lesson | 教訓 | Extracted insight from one or more observations: pattern identified, anomaly noted | Auto-scan + manual input | POST /input/lesson, /learning/auto/scan-lessons | Timestamped, tagged with confidence |
| 3 | Hypothesis | 假說 | Testable claim derived from lessons: “if condition X, then outcome Y” | Auto-generated (L2+) or manual | POST /input/hypothesis, /learning/auto/scan-hypotheses | Must be falsifiable; requires experiment to validate |
| 4 | Experiment | 實驗 | Controlled test in Paper Trading to validate or reject a hypothesis | Semi-automatic | POST /input/experiment, /learning/experiment/{id}/approve | Isolated PnL tracking; minimum duration/trade count |
| 5 | Verdict | 裁定 | Conclusion from experiment: confirmed, rejected, or inconclusive | Analyst proposes, Operator confirms for high-impact | POST /learning/hypothesis/{id}/verdict | Updates strategy parameters or generates new hypotheses |


# §3 Analyst 進化引擎 L1–L5 / Analyst Evolution Engine

The Analyst Agent evolves through five maturity levels. Each level unlocks new capabilities and requires demonstrated competence at the previous level before promotion.


## §3.1 L1 復盤 / Post-Trade Review

**解鎖條件：**系統啟動即可用（當前狀態）
- Record observations on every round-trip completion (auto, Session 8 E1)
- Compute basic metrics: win rate, Sharpe ratio, max drawdown, average holding time
- Tag each observation with regime, strategy, instrument, and session
- Identify obvious patterns: time-of-day effects, strategy-instrument mismatch
- **計算層級：**L0 only (zero cost)


## §3.2 L2 模式發現 / Pattern Discovery

**解鎖條件：**500+ observations accumulated; win_rate > 20%
- Cross-strategy performance comparison under same regime
- Regime-specific strategy ranking (which strategy works best in trending vs ranging)
- Cost attribution analysis: which strategies have best net-of-cost performance
- Correlation discovery: identify relationships between market features and trade outcomes
- Anomaly detection: flag unusual outcomes for deeper analysis
- **計算層級：**L1 (local Ollama) for pattern recognition


## §3.3 L3 假說實驗 / Hypothesis & Experiment

**解鎖條件：**L2 running for 2+ weeks; 3+ confirmed patterns
- Generate testable hypotheses from L2 patterns (e.g., “MA crossover performs 40% better in trending regimes with >2x average volume”)
- Design controlled experiments in Paper Trading with isolated tracking
- Statistical validation: minimum sample size, significance testing
- Experiment lifecycle: proposed → approved → running → completed → verdict
- **計算層級：**L1.5 for hypothesis generation; L0/L1 for experiment execution


## §3.4 L4 策略進化 / Strategy Evolution

**解鎖條件：**3+ validated hypotheses from L3; positive experiment ROI
- Evolve strategy parameters based on validated experiment results
- Create new strategy variants (e.g., MA Crossover v2 with volume filter)
- Cross-strategy transfer learning: apply insights from one strategy to improve others
- Regime transition prediction: use accumulated pattern data to anticipate regime changes
- Strategy incubation: auto-deploy promising variants to Paper Trading
- **計算層級：**L2 (full cloud) for complex strategy evaluation


## §3.5 L5 元學習 / Meta-Learning

**解鎖條件：**6+ months operational data; sustained positive live performance; Operator explicit approval
- Learn how to learn better: optimize the learning pipeline’s own parameters
- Identify blind spots in Analyst’s analysis methodology
- Self-calibrate confidence levels based on historical accuracy
- Propose improvements to observation recording, hypothesis generation, and experiment design
- Meta-hypothesis: hypotheses about the learning process itself
- **計算層級：**L2 + Operator review for all meta-learning proposals


# §4 策略孵化流程 / Strategy Incubation Pipeline

New strategies emerge from the learning pipeline and follow a structured path from idea to live deployment. This is the maximum extent of learning autonomy—and the most important boundary.


| **#** | **Stage** | **Owner** | **Description** | **Automation** |
|---|---|---|---|---|
| 1 | Idea Generation | Analyst L3+ | Pattern or hypothesis suggests a new strategy approach | Automatic |
| 2 | Design | Analyst + Strategist | Define strategy logic, parameters, entry/exit rules | Semi-automatic |
| 3 | Paper Deployment | Analyst (auto-deploy) | Deploy to Paper Trading Engine with isolated PnL tracking | Automatic (no Operator approval needed) |
| 4 | Validation Gate | Guardian | 4 weeks + 500 trades + positive net PnL + >30% win rate + Sharpe >0.5 | Automatic evaluation |
| 5 | Live Promotion | Guardian verifies gate | If gate criteria ALL met simultaneously, strategy becomes live-eligible | Auto-promote (first new type needs Operator approval) |
| 6 | Live Monitoring | Analyst + Guardian | Continuous performance monitoring; auto-pause on 10 consecutive losses | Automatic |
| 7 | Retirement | Guardian or Analyst | Strategy removed when consistently underperforming alternatives | Semi-automatic (logged) |


## §4.1 孵化邊界規則 / Incubation Boundary Rules
- **Paper deployment is autonomous: **Analyst can deploy any strategy variant to paper without Operator approval
- **Live promotion is gated: **all 5 gate criteria must be simultaneously met; no exceptions
- **First-of-type requires Operator: **the first live deployment of a previously unseen strategy type requires explicit Operator approval
- **Subsequent deployments of same type are autonomous: **once a strategy type has been approved for live, new variants of that type auto-promote if gate criteria met
- **Failed experiments are valuable: **rejected hypotheses and failed strategies are recorded as negative results to prevent re-testing


# §5 跨策略遷移學習 / Cross-Strategy Transfer Learning

Insights from one strategy can improve others. The Analyst identifies transferable patterns and proposes cross-pollination experiments.


## §5.1 遷移學習類型 / Transfer Learning Types
- **Parameter transfer: **optimal ATR multiplier discovered for MA Crossover may apply to BB Breakout in similar regimes
- **Filter transfer: **volume filter validated in one strategy tested across all trend-following strategies
- **Regime knowledge transfer: **regime transition patterns learned globally shared across all strategies
- **Exit rule transfer: **time-stop optimization from one strategy applied as default across portfolio


## §5.2 遷移邊界 / Transfer Boundaries
- Transfer proposals require Analyst L3+ capability
- Each transfer is treated as a new hypothesis requiring its own validation experiment
- Cross-family transfers (e.g., spot insight applied to perps) require extra validation due to different risk profiles
- Transfers cannot violate P0/P1 risk parameters of the target strategy


# §6 Regime 轉換預測 / Regime Transition Prediction

At Analyst L4+, the learning engine begins predicting regime transitions rather than just detecting them after the fact.


## §6.1 預測信號 / Prediction Signals
- Bollinger Band width compression/expansion rate
- Volume profile divergence from recent average
- Order book depth asymmetry trends
- Cross-asset correlation shifts (e.g., BTC-ETH correlation breaking down)
- Macro event proximity (FOMC, CPI within 24h)
- Funding rate divergence from historical mean


## §6.2 預測邊界 / Prediction Boundaries
- **Predictions are probabilistic: **expressed as confidence % (never binary YES/NO)
- **Low-confidence predictions (<50%) are informational only: **no action taken, logged for review
- **Medium-confidence (50–75%) trigger defensive posture: **Guardian tightens stops, reduces new entries
- **High-confidence (>75%) trigger proactive repositioning: **strategy switching, position adjustment
- **All predictions are tracked for calibration: **predicted vs actual regime tracked to improve future accuracy


# §7 學習數據生命週期 / Learning Data Lifecycle


## §7.1 數據保留 / Data Retention
- **Observations: **indefinite retention (raw source of truth)
- **Lessons: **indefinite retention; tagged as active/deprecated
- **Hypotheses: **indefinite retention; tagged as pending/confirmed/rejected/inconclusive
- **Experiments: **indefinite retention including full trade-by-trade records
- **Verdicts: **indefinite retention; linked to originating hypothesis and experiment


## §7.2 數據品質標記 / Data Quality Tagging
- **fact: **objectively verifiable data (price, volume, fill, timestamp)
- **inference: **derived from facts with defined methodology (regime detection, correlation)
- **hypothesis: **proposed but unvalidated claim
- **Root Principle #8: **all conclusions must carry these tags; mixing them is a governance violation


# §8 Analyst 自主權邊界 / Analyst Autonomy Boundaries


## §8.1 Analyst 可自主執行 / Analyst Can Autonomously
- Record observations (fully automatic)
- Extract lessons from observations (auto-scan enabled)
- Generate hypotheses from patterns (L2+ required)
- Deploy experiments to Paper Trading (no Operator pre-approval)
- Evaluate experiment results and propose verdicts
- Recommend strategy parameter adjustments
- Auto-deploy validated strategy variants to paper
- Track and report learning pipeline metrics


## §8.2 Analyst 禁止自主 / Analyst Cannot Autonomously
- Modify live strategy parameters directly (must go through Guardian validation)
- Promote strategies to live that haven’t passed the gate criteria
- Disable or modify P0/P1 risk controls
- Delete or modify historical observations (append-only)
- Override Guardian’s risk-based rejections
- Access execution systems directly (no order placement capability)
- Modify its own evolution level (promotion requires demonstrated criteria)


## §8.3 需要 Operator 批准 / Requires Operator Approval
- First-ever live deployment of a new strategy type
- Changes to Paper→Live gate criteria themselves
- Analyst L5 meta-learning proposals that change the learning pipeline
- Cross-product-family strategy transfers
- Increasing AI compute budget ceiling for learning activities


# §9 跨文件參照 / Cross-Reference


| **Document** | **中文** | **Relationship** |
|---|---|---|
| DOC-01 V2 | 憲法 | Root Principle #7 (學習≠自作主張) and #8 (事實/推斷/假說區分) are foundational to this document |
| DOC-04 V2 | 能力藍圖 | Capability E (Continuous Learning) implemented by this document’s framework |
| DOC-06 V2 | 變更治理 | How learning-driven changes are governed and approved |
| DOC-08 V1 | 實施橋樑 | AI budget management that constrains learning compute usage |
| EX-01 V2 | 風控邊界 | Risk framework that constrains strategy incubation and live promotion |
| EX-06 V1 | Multi-Agent | Analyst Agent role definition and inter-Agent communication |
| EX-07 V1 | 感知平面 | Data sources that feed observations; freshness and quality tagging |

*End of Document — EX-05 Learning Boundary V2.0 — OpenClaw/Bybit*
