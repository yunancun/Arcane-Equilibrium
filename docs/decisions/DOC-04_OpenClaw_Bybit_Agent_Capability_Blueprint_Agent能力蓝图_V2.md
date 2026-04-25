**DOC-04**

Agent Capability Blueprint

Agent 能力蓝图

OpenClaw / Bybit AI Agent Trading System

**Version 2.0**

2026-03-29

*Classification: Internal — Governance Document*


# 修訂歷史 / Revision History

| **Date** | **Ver** | **Author** | **Changes** |
|---|---|---|---|
| 2026-03-24 | 1.0 | Claude / Operator | Initial capability blueprint (H0–H5 + I) |
| 2026-03-26 | 1.1 | Claude / Operator | Minor alignment with DOC-01 V1 constitution |
| 2026-03-29 | 2.0 | Claude / Operator | Major expansion: A–J capabilities, 6 product families, Multi-Agent, Analyst evolution L1–L5, adversarial market awareness, portfolio intelligence, session awareness, regime prediction |


# §1 用途與範圍 / Purpose & Scope

This document defines the complete capability blueprint for the OpenClaw/Bybit AI Agent trading system. It serves as the authoritative reference for what the Agent can do, should do, and must not do—across all product families, strategies, market conditions, and operational phases.

**V2 擴展範圍：** V1 僅覆蓋 H0–H5 + I 治理管線。V2 正式納入 CLAUDE.md A–J 十大能力目標、全品類自主交易、Multi-Agent 編排、對抗性市場意識、組合層智能、Analyst 進化引擎、時段意識、零成本可運行原則等全部內容。

**與其他文件關係：** 本文件描述「能做什麼」（What）；DOC-01 憲法定義「根原則」（Why）；DOC-02 邊界定義「在哪裡做」（Where）；DOC-08 實施橋樑定義「怎麼做」（How）。


# §2 十大能力目標 / Ten Capability Goals (A–J)

The following ten goals constitute the complete capability target of the system. Each goal is assigned a current completion level (as of 2026-03-29 Session 12) and a target maturity phase.


| **ID** | **中文名稱** | **English Name** | **Current** | **Target** | **Gate Phase** |
|---|---|---|---|---|---|
| **A** | 自主交易執行 | Autonomous Trade Execution | 60% | M/N | Supervised→Autonomous Live |
| **B** | 成本與收益感知 | Cost & Revenue Awareness | 50% | M | Supervised Live |
| **C** | 計算路徑智能分級 | Compute Path Tiering | 30% | M | Supervised Live |
| **D** | 自我感知能力 | Self-Observability | 20% | L/M | Paper→Supervised |
| **E** | 持續學習能力 | Continuous Learning | 5% | M/N | Supervised→Autonomous Live |
| **F** | 日/週/月經營報告 | Operational Reporting | 30% | M | Supervised Live |
| **G** | Agent 自主交易 | Agent Autonomous Trading | 55% | M/N | Supervised→Autonomous Live |
| **H** | 對抗性市場意識 | Anti-Adversarial Trading | 60% | M | Supervised Live |
| **I** | AI 注意力稅 | AI Attention Tax | 10% | M | Supervised Live |
| **J** | GUI 運營駕駛艙 | GUI Operator Console | 80% | L | Paper Trading |


## §2.1 [A] 自主交易執行 / Autonomous Trade Execution

The Agent autonomously completes order placement, cancellation, amendment, and position management. Every execution must pass the full governance pipeline: H0 local deterministic check → H1–H5 AI governance → Decision Lease → execution gate. No gate may be skipped under any circumstances.

### 能力要點 / Capability Points
- Supports all 6 Bybit V5 product families: spot, margin, perp_linear, perp_inverse, options, other_derivatives_reserved
- Supports 10+ order types: market, limit, conditional, tp_sl_order, tp_sl_position, trailing_stop, reduce_only, post_only, iceberg, twap, batch
- Margin modes: cross, isolated, portfolio
- Position modes: one_way, hedge
- Order lifecycle management: submission → working → partial_fill → fill/cancel/reject
- Paper Trading engine simulates all of the above with realistic slippage (0.05%) and fee models (taker 0.055%, maker 0.02%)

### 約束條件 / Constraints
- Must pass H0 → AI governance → Decision Lease → execution gate (no shortcuts)
- Cannot bypass any gate even under time pressure (“market is moving” is not a valid bypass reason)
- Cannot execute on product families not yet authorized by Operator
- Cannot modify system_mode or execution_authority


## §2.2 [B] 成本與收益感知 / Cost & Revenue Awareness

The system tracks net PnL, not gross PnL. Every decision must be evaluated against the question: after deducting all real costs, does this trade still have positive expected value?

### 能力要點 / Capability Points
- Mandatory cost components: AI API call cost, Bybit trading fees, estimated slippage, equipment depreciation, electricity, infrastructure
- net_realized_pnl = realized_pnl − total_fees (Session 9 B2)
- AI cost attribution: each position carries ai_cost_attributed_usd from L1/L1.5/L2 calls (Session 10 B1)
- Fee optimization: maker-priority execution reduces cost from ~21bps to ~12bps
- Cost-edge ratio monitoring per position (see Capability I: AI Attention Tax)
- Daily/weekly/monthly cost breakdown in operational reports

### 約束條件 / Constraints
- Every trade decision must have a positive net expected value after all costs
- AI consultation is gated: win_rate > 20% before enabling L1.5/L2 calls (current decision)
- Zero-cost runnable principle: L0 + L1 (local Ollama) must be sufficient for basic operation


## §2.3 [C] 計算路徑智能分級 / Compute Path Intelligent Tiering

Every computation is routed to the most cost-effective tier that can handle it. The Agent proactively scans market conditions (not just passively reviewing proposals).

### 能力要點 / Capability Points
- L0: Pure local deterministic (lowest latency, zero cost) — freshness, health gates, risk envelope, eligibility
- L1: Local Ollama (Qwen2.5 7B, 12GB memory limit, systemd isolation, 3s timeout) — regime detection, pattern recognition
- L1.5: Low-cost cloud (Haiku + Perplexity, ~$0.01–0.05/call) — market commentary, news sentiment
- L2: Full cloud (Sonnet/Opus) — complex multi-factor analysis, strategy evolution decisions
- Every call has cost accounting integrated into net PnL
- 4-layer search degradation: L0 cache → L1 local → L1.5 Perplexity → L2 full search

### 約束條件 / Constraints
- L0 always runs first; higher tiers only when L0 cannot resolve
- AI budget: adaptive + ROI-based, conservative mode $2/day ceiling
- Hardware: AMD AI MAX 395 + 128GB unified memory; Ollama: MemoryMax=12G, CPUQuota=150%


## §2.4 [D] 自我感知能力 / Self-Observability

The Agent monitors its own hardware, network, and software health. When the system is unhealthy, it proactively degrades or pauses—system health comes before market judgment (Root Principle #5).

### 能力要點 / Capability Points
- Hardware awareness: CPU usage, memory pressure, disk I/O
- Network awareness: REST latency, WebSocket stability, public egress IP, packet loss rate
- Software awareness: module-level bottleneck detection, database query latency, script execution time
- Health gate (verified Session 8 D1): pre-trade health check blocks execution when system is unhealthy
- Graceful degradation: reduce trading frequency, pause new entries, maintain existing positions only

### 約束條件 / Constraints
- System health gate is non-bypassable (P0 priority)
- Degradation is automatic and does not require Operator approval


## §2.5 [E] 持續學習能力 / Continuous Learning

The Agent records the full context of every decision, performs attribution analysis on outcomes, generates testable hypotheses, proposes experiments, and accumulates reusable experience. Learning ≠ acting unilaterally (Root Principle #7).

### 能力要點 / Capability Points
- Auto-observation recording: PipelineBridge emits observation on every round-trip completion (Session 8 E1, Session 12 E1a/E1b)
- Tick-path coverage: risk_auto_close, time stops, soft stops all trigger observation recording (Session 12 E1b)
- Attribution: strategy error vs. timing error vs. execution error vs. cost error
- Learning pipeline: Observation → Lesson → Hypothesis → Experiment → Verdict
- Review queue: human-in-the-loop for high-impact lessons and experiments
- AI consultation for hypothesis evaluation (POST /learning/review/{id}/ai-consult)

### 約束條件 / Constraints
- Learning cannot auto-modify live configuration, unlock permissions, or deploy code
- All conclusions must distinguish: fact / inference / hypothesis (Root Principle #8)
- Strategy evolution proposals require paper validation before live deployment


## §2.6 [F] 日/週/月經營報告 / Operational Reporting

Regular reporting decomposes performance: which trades made money, which lost money, which costs can be optimized. Includes error attribution and actionable optimization suggestions.

### 能力要點 / Capability Points
- Daily report: position summary, PnL breakdown, strategy performance ranking
- Weekly report: trend analysis, cost optimization opportunities, learning insights
- Monthly report: comprehensive review, strategy evolution assessment, ROI analysis
- API routes: GET /business/daily, /business/summary
- Planned: OpenClaw Cron daily auto-report → Telegram push at UTC 00:00

### 約束條件 / Constraints
- Reports must show net PnL (not gross)
- Reports must include AI cost breakdown


## §2.7 [G] Agent 自主交易 / Agent Autonomous Trading

Within the risk control framework, the Agent autonomously decides: which instrument, which strategy, which timing, what position size, and what parameters. The Operator sets hard limits only; the Agent makes all tactical decisions.

### 能力要點 / Capability Points
- Market scanner: scans 650+ Bybit symbols every 5 minutes for trading opportunities
- Strategy auto-deployer: matches market conditions to optimal strategy type
- Multi-symbol support: concurrent positions across multiple instruments
- Autonomous strategy selection: MA Crossover, Grid, Funding Arbitrage, BB Breakout, RSI Divergence, Delta-Neutral
- Autonomous parameter setting: confidence thresholds, position sizes (ATR-based), stop levels
- Auto-pause on consecutive losses: 10-loss threshold triggers strategy suspension (Session 8 G1)
- Three-tier priority risk control: P0 product-specific > P1 global > P2 Agent adaptive

### 約束條件 / Constraints
- Cannot breach Operator-set hard limits (P0/P1)
- Cannot enable unauthorized product families
- Cannot disable hard stops
- Cannot modify system_mode
- P2 Agent adaptive parameters must stay within effective = min(P0 ?? P1, P1)


## §2.8 [H] 對抗性市場意識 / Anti-Adversarial Trading Awareness

The Agent operates with awareness that the market contains adversarial actors who profit from stop hunting, liquidity traps, and information asymmetry. The system employs multi-layer defenses.

### 能力要點 / Capability Points
- Dual-layer stops: hard stop (absolute defense, P1 global ceiling) + soft stop (Agent evaluates: gradual decline vs. spike, correlated asset movement)
- Stop concealment: never place stop orders on exchange order book; all stops are local tick()-triggered
- Anti-hunt measures: ATR-based dynamic stops + random offset + fake breakout detection + liquidity-aware exit
- Non-standard position sizing: avoid round-number positions that reveal algorithmic presence
- Regime-aware stop/TP/time adjustment: volatile →1.5× stops, squeeze →0.6× stops (Session 11 R1)
- ATR dynamic stop integration: PipelineBridge._on_position_open() calls StopManager.track_position (Session 8 H1)

### 約束條件 / Constraints
- Hard stops can never be disabled or loosened beyond P1 limits
- Stop concealment is mandatory for all position types


## §2.9 [I] AI 注意力稅 / AI Attention Tax

Every open position consumes AI computational resources (monitoring, evaluation, decision-making). This cost must be explicitly tracked as part of the true holding cost.

### 能力要點 / Capability Points
- cost_edge_ratio = total_holding_cost / initial_expected_edge
- Grade system: A (<0.2) / B (<0.4) / C (<0.6) / D (<0.8) / F (≥0.8)
- Auto-close trigger: when cost_edge_ratio exceeds threshold AND edge > taker close fee (Session 12 F2)
- Tax-free period: first 30 minutes exempt (new position ramp-up)
- Strategy-differentiated thresholds: high-frequency strategies have tighter thresholds
- Close cost gate: edge_usd must exceed notional × 0.00055 (taker fee) to prevent net-loss closes
- Fill fragmentation fix: tail-quantity check reduces fills per order from 25–30 to ≤10, lowering attention tax burn rate (Session 12 F1)

### 約束條件 / Constraints
- Agent naturally prefers low-maintenance strategies
- Positions with F-grade cost_edge_ratio should be flagged for immediate review


## §2.10 [J] GUI 運營駕駛艙 / GUI Operator Console & Learning Cockpit

The unified operator interface provides complete visibility and control across all system functions.

### 能力要點 / Capability Points
- 10-Tab professional console: Overview, Control Plane, System Health, Risk & Business, Learning Cockpit, Paper Trading, Bybit Demo, Net PnL, Audit Trail, Strategy
- Real API calls (not static mocks): concurrent fetch to 10+ endpoints
- Learning Cockpit 5 sub-tabs: Observation, Lesson, Hypothesis, Experiment, Review Queue
- Paper Trading Dashboard: session control + PnL cards + positions/orders/fills/audit
- Unified console at /console: Trading Dashboard + OpenClaw Gateway + AI Cost sidebar
- Dual-layer explanation: hover tooltips + expandable detail panels
- Three-layer information density: summary → detail → raw data
- 6 AI provider configurations supported
- Chinese status labels with hover translations

### 約束條件 / Constraints
- GUI → Control API → Agent logic (GUI never bypasses API)
- Confirmation dialogs required for all state-changing actions


# §3 全品類自主交易 / Full-Category Autonomous Trading

The Agent is designed to operate across all Bybit V5 product families. Each family has distinct risk characteristics, margin requirements, and execution semantics.


## §3.1 產品族矩陣 / Product Family Matrix

| **Family** | **中文** | **Description** | **Current Level** | **Risk Tier** |
|---|---|---|---|---|
| spot | 現貨 | No leverage, no liquidation, safest | observe_only | Low |
| margin | 現貨保證金 | Leverage + borrowing interest + liquidation risk | unsupported | Medium |
| perp_linear | 線性永續 | USDT/USDC settled, 1–125× leverage, funding rate, primary arena | shadow_ready | High |
| perp_inverse | 反向永續 | Coin-settled, leverage, funding rate | unsupported | High |
| options | 期權 | Buyer: limited loss; Seller: unlimited risk; Greeks exposure | unsupported | Very High |
| other_derivatives | 其他衍生品 | Futures with expiry, reserved | unsupported | High |


## §3.2 能力層級演進 / Capability Level Progression

Each product family progresses through six capability levels. Promotion requires demonstrated competence at the current level.

| **Level** | **中文** | **Description** |
|---|---|---|
| unsupported | 未支援 | No capability implemented for this family |
| observe_only | 僅觀察 | Can receive and process market data; no orders |
| shadow_ready | 影子就緒 | Can generate shadow decisions; no execution |
| demo_ready | 演示就緒 | Can execute on Bybit testnet/sandbox |
| live_guarded_ready | 受護上線 | Can execute live with strict guardrails |
| live_ready | 完全上線 | Full autonomous live execution within P0/P1 limits |


## §3.3 訂單類型支援 / Order Type Support

The Agent supports the full Bybit V5 order type matrix. Each order type maps to specific strategic use cases.

| **Type** | **中文** | **Description** | **Families** | **Status** |
|---|---|---|---|---|
| market | 市價單 | Immediate execution at best available price | All families | Active |
| limit | 限價單 | Execute at specified price or better | All families | Active |
| conditional | 條件單 | Trigger-based order (stop/take-profit) | Perps, margin | Active |
| tp_sl_order | 止盈止損單 | Attached TP/SL to specific order | Perps | Active |
| tp_sl_position | 持倉TP/SL | Position-level TP/SL | Perps | Planned |
| trailing_stop | 追蹤止損 | Dynamic trailing stop | Perps | Planned |
| reduce_only | 僅減倉 | Can only reduce existing position | All leveraged | Active |
| post_only | 僅Maker | Rejected if would take liquidity | All families | Active |
| iceberg | 冰山單 | Large order split into visible chunks | Perps, spot | Planned |
| twap | TWAP | Time-weighted average price execution | Perps | Planned |
| batch | 批量單 | Multiple orders in single API call | All families | Planned |


# §4 策略自主選擇與參數自設 / Strategy Autonomy

The Agent autonomously selects, deploys, tunes, and retires strategies based on market conditions. The Operator does not pre-approve individual trades or strategy selections.


## §4.1 策略类型庫 / Strategy Type Library

| **Strategy** | **Category** | **Description** | **Optimal Regime** | **Status** |
|---|---|---|---|---|
| MA Crossover | Trend | Moving average crossover signals | Trending regimes | Active |
| Grid Trading | Mean-reversion | Place orders at geometric intervals | Ranging regimes | Active |
| Funding Arb | Arbitrage | Capture funding rate payments | High funding rate | Active |
| BB Breakout | Momentum | Bollinger Band breakout signals | Volatility expansion | Active |
| RSI Divergence | Reversal | Price-RSI divergence detection | Regime transitions | Active |
| Delta-Neutral | Hedging | Maintain delta-neutral portfolio | All regimes | Planned |


## §4.2 自主決策範圍 / Agent Autonomous Decision Scope

The Agent has full autonomy over the following tactical decisions, within P0/P1 hard limits:
- Instrument selection: which symbol to trade, based on scanner scoring
- Strategy selection: which strategy type matches current regime
- Parameter setting: confidence thresholds, MA periods, grid spacing, stop distances
- Position sizing: ATR-based dynamic sizing with score weighting
- Entry timing: when to enter based on signal strength and market conditions
- Exit timing: profit targets, time stops, regime-change exits, attention-tax exits
- Strategy retirement: auto-pause on consecutive losses (10-loss threshold)


## §4.3 新策略孵化流程 / New Strategy Incubation

New strategies follow a structured incubation pipeline. No Operator pre-approval is needed for paper deployment; Operator approval is only required for the first live deployment of a previously unseen strategy type.
- Hypothesis generation: Analyst identifies potential new strategy from pattern analysis
- Paper validation: strategy deployed in Paper Trading Engine with isolated PnL tracking
- Gate criteria: 4 weeks + 500 trades + positive net PnL + >30% win rate + Sharpe > 0.5
- Auto-promotion: if gate criteria met, strategy automatically becomes live-eligible
- Live deployment: executes within existing P0/P1 risk framework


# §5 Multi-Agent 編排架構 / Multi-Agent Orchestration

OpenClaw serves as the Conductor (not an independent Agent), leveraging its existing Multi-Agent routing, Cron scheduling, web-pilot, and Memory capabilities. Five specialized Agents collaborate under OpenClaw’s orchestration.


## §5.1 Agent 角色矩陣 / Agent Role Matrix

| **Agent** | **中文** | **Responsibility** | **Data Access** | **Authority** |
|---|---|---|---|---|
| Scout | 偵察員 | Market scanning, data collection, event monitoring | Market data, news, events | Read-only |
| Strategist | 策略師 | Strategy selection, parameter optimization, signal generation | All market data + learning | Strategy commands |
| Guardian | 守護者 | Risk enforcement, stop management, circuit breakers | All system state | Override authority |
| Analyst | 分析師 | Post-trade analysis, learning, hypothesis generation | Trade history + observations | Learning writes |
| Executor | 執行者 | Order submission, amendment, position management | Decision Leases only | Order execution |


## §5.2 衝突仲裁 / Conflict Arbitration

When Agents disagree, Guardian overrides Strategist. Specifically:
- Guardian veto is final: if Guardian determines risk limits would be breached, Strategist’s proposal is rejected
- Strategist can appeal: by submitting a hypothesis to the learning pipeline for future evaluation
- Executor only acts on valid Decision Leases: no direct orders from Strategist bypass the lease system


## §5.3 資源受限模式 / Resource-Constrained Mode

When running on L0 + L1 only (zero external API cost), a single Ollama instance serves multiple Agent roles sequentially. OpenClaw’s Cron scheduler ensures non-overlapping execution windows.


# §6 Analyst 進化引擎 / Analyst Evolution Engine (L1–L5)

The Analyst Agent evolves through five levels of analytical maturity. Each level builds on the previous, requiring demonstrated capability before promotion.


| **Level** | **中文** | **Name** | **Capabilities** | **Prerequisites** |
|---|---|---|---|---|
| L1 | 復盤 | Post-Trade Review | Record observations, compute basic metrics (win rate, Sharpe, max drawdown). Identify obvious patterns in trade outcomes. | Auto-observation on round-trip (E1) |
| L2 | 模式發現 | Pattern Discovery | Cross-strategy performance comparison, regime-specific analysis, cost attribution. Identify correlations between market conditions and strategy performance. | Learning pipeline + AI consultation |
| L3 | 假說實驗 | Hypothesis & Experiment | Generate testable hypotheses from L2 patterns. Design and run controlled experiments in Paper Trading. Statistical validation of results. | Experiment framework + paper engine |
| L4 | 策略進化 | Strategy Evolution | Evolve strategy parameters based on L3 results. Create new strategy variants. Cross-strategy transfer learning. Regime transition prediction. | Strategy auto-deployer + full L2 cloud |
| L5 | 元學習 | Meta-Learning | Learn how to learn better. Optimize the learning pipeline itself. Identify blind spots in the Analyst’s own analysis. Self-calibrate confidence levels. | Full system access + Operator review |

**Current status: **L1 operational (auto-observation recording active since Session 8). L2–L5 are design-complete but pending data accumulation and win_rate > 20% gate.


# §7 組合層智能 / Portfolio-Level Intelligence

Beyond individual position management, the Agent must reason about the portfolio as a whole—managing correlation risk, capital allocation, and aggregate exposure.


## §7.1 相關性監控 / Correlation Monitoring
- Track pairwise correlation between all open positions
- Alert when portfolio correlation exceeds threshold (e.g., >0.7 average pairwise correlation)
- Reduce exposure to correlated positions during regime transitions


## §7.2 資本分配 / Capital Allocation
- Dynamic capital allocation based on strategy conviction scores
- Higher-scoring opportunities receive proportionally larger allocations
- Maximum single-position allocation capped by P1 limits
- Reserve capital buffer for unexpected opportunities or margin calls


## §7.3 組合級風控 / Portfolio-Level Risk Control
- Aggregate max drawdown limit across all positions
- Sector/category concentration limits
- Total margin utilization ceiling
- Portfolio-level Sharpe ratio monitoring


# §8 時段意識 / Session Awareness

Crypto markets are 24/7 but exhibit distinct behavioral patterns across major trading sessions. The Agent adapts its behavior accordingly.


| **Session** | **Time (UTC)** | **Characteristics** | **Agent Adaptation** |
|---|---|---|---|
| Asia | 00:00–08:00 UTC | Generally lower volatility, altcoin-heavy | Wider stops, smaller positions |
| Europe | 07:00–16:00 UTC | Increasing volume, trend initiation | Standard parameters |
| Americas | 13:00–21:00 UTC | Highest volume, most volatile | Tighter risk management |
| Weekend | Sat–Sun | Low liquidity, wider spreads, flash crash risk | Reduced position sizes, wider stops |


## §8.1 Crypto 事件日曆 / Crypto Event Calendar

The Agent maintains awareness of scheduled events that materially impact markets:
- Token Unlock: large supply releases that may cause selling pressure
- New listings: exchange listing announcements that trigger volatility
- Macro events: FOMC rate decisions, CPI releases, employment data
- Protocol events: hard forks, mainnet launches, governance votes
- **Pre-event behavior: **reduce leverage, tighten stops, pause new entries for high-impact events


# §9 Regime 轉換預測 / Regime Transition Prediction

The Agent detects and predicts transitions between market regimes, enabling proactive strategy switching rather than reactive adaptation.


## §9.1 Regime 類型 / Regime Types

| **Regime** | **中文** | **Description** | **Preferred Strategy** |
|---|---|---|---|
| trending | 趨勢 | Strong directional movement with momentum | MA Crossover, BB Breakout |
| ranging | 震盪 | Price oscillating within defined boundaries | Grid Trading, Mean Reversion |
| volatile | 高波動 | Large price swings without clear direction | Wider stops, smaller positions |
| squeeze | 擠壓 | Contracting volatility, pending breakout | Tighter time stops (~14h vs 48h default) |
| unknown | 未知 | Insufficient data or conflicting signals | No new entries (cold-start protection) |


## §9.2 Regime 感知三維調整 / Regime-Aware Triple Adjustment

Session 11 R1 introduced regime-aware multipliers for stops, take-profit, and time limits:
- **Stop multiplier: **volatile →1.5×, squeeze →0.6×, trending →1.0× (default)
- **Take-profit multiplier: **trending →1.3× (let winners run), volatile →0.8× (take profits early)
- **Time stop multiplier: **squeeze ~14h, trending ~72h, default 48h


## §9.3 轉換預測能力 / Transition Prediction (Planned)

Future Analyst L4 capability will enable regime transition prediction based on:
- Volatility compression/expansion patterns (Bollinger Band width)
- Volume profile changes
- Order book imbalance trends
- Cross-asset correlation shifts
- Macro event proximity


# §10 零成本可運行原則 / Zero-Cost Runnable Principle

The system must be fully operational at zero external API cost using L0 (deterministic) + L1 (local Ollama). Cloud-based L1.5 and L2 tiers are only activated after demonstrating positive returns at the lower tiers.


## §10.1 分層啟用邏輯 / Tiered Activation Logic
- L0 + L1 startup: zero external cost, basic trading with local regime detection
- Positive net PnL sustained for 2+ weeks: L1.5 (Haiku + Perplexity) unlocked
- L1.5 demonstrates positive ROI on AI spend: L2 (Sonnet/Opus) unlocked for high-value decisions
- Continuous ROI monitoring: if AI spend ROI drops below threshold, auto-downgrade to lower tier


## §10.2 AI 預算管理 / AI Budget Management
- **Conservative mode: **$2/day ceiling
- **Adaptive mode: **budget scales with demonstrated ROI
- **ROI tracking: **(revenue_attributed_to_AI − AI_cost) / AI_cost
- **Auto-downgrade: **if ROI < 1.0 for 3 consecutive days, drop one tier


# §11 Paper → Live 閘門 / Paper-to-Live Gate

The transition from paper trading to live execution is governed by strict, measurable criteria. No subjective judgment; all criteria must be simultaneously met.


| **Criterion** | **中文** | **Threshold** | **Rationale** |
|---|---|---|---|
| Duration | 運行時間 | ≥ 4 weeks | Sufficient market regime exposure |
| Trade count | 交易筆數 | ≥ 500 round-trip trades | Statistical significance |
| Net PnL | 淨損益 | Positive (after all costs) | Proven profitability |
| Win rate | 勝率 | > 30% | Consistent signal quality |
| Sharpe ratio | 夏普比率 | > 0.5 | Risk-adjusted return quality |

**當前狀態：**Paper Trading 運行中。勝率尚未達標（Session 12 修復後正在積累新數據）。等待修復後的策略在新 regime 感知規則下運行數週後再評估。


# §12 治理管線映射 / Governance Pipeline Mapping

The complete pipeline from market data to execution, showing how each capability integrates:


| **Pipeline Stage** | **Capability** | **Agent** | **Implementation** |
|---|---|---|---|
| Market Data | D (Self-Observability) | Scout Agent | Bybit WS/REST → Observer → freshness tagging |
| H0 Local Judgment | A (Execution) + D | Guardian Agent | Freshness, health gate, eligibility, risk envelope |
| H1–H5 AI Governance | C (Compute Path) | Strategist Agent | Thought gate → budget → model router → governor → cost logging |
| Decision Lease | G (Agent Trading) | Strategist → Executor | Shadow-only lease with time-to-live + revocation |
| Execution | A (Execution) | Executor Agent | Paper engine / Bybit sandbox / Live (future) |
| Post-Trade | E (Learning) + B (Cost) | Analyst Agent | Observation → Attribution → Learning pipeline |
| Reporting | F (Reports) + I (Tax) | Analyst Agent | PnL decomposition → Cost analysis → Reports |
| GUI | J (Console) | Operator | Visibility + Control + Audit |


# §13 跨文件參照 / Cross-Reference to Other Governance Documents


| **Document** | **中文名稱** | **Relationship to DOC-04** |
|---|---|---|
| DOC-01 V2 | 憲法 | Root principles that constrain all capabilities in this document |
| DOC-02 V2 | 邊界定義 | H0–H5 governance boundary details; Multi-Agent boundary precursors |
| DOC-06 V2 | 變更治理 | How capabilities evolve: what Agent can change vs. Operator must approve |
| DOC-08 V1 | 實施橋樑 | Technical implementation of L0/L1/L1.5/L2 compute paths; deployment details |
| EX-01 V2 | 風控邊界 | P0/P1/P2 risk framework that constrains capabilities G and H |
| EX-05 V2 | 學習邊界 | Analyst L1–L5 evolution rules that govern capability E |
| EX-06 V1 | Multi-Agent 編排 | Detailed Agent roles, communication protocol, conflict arbitration |
| EX-07 V1 | 感知平面 | Data sources, freshness model, and Agent data access matrix |


# §14 附錄 / Appendix

## A. 執行動作權限矩陣 / Execution Action Permission Matrix

| **Action** | **中文** | **Description** | **Minimum Capability Level** |
|---|---|---|---|
| new_order | 新下單 | Submit new order | shadow_ready+ |
| cancel | 撤單 | Cancel existing order | shadow_ready+ |
| amend | 改單 | Modify existing order | shadow_ready+ |
| reduce_only | 僅減倉 | Reduce position only | shadow_ready+ |
| increase_position | 加倉 | Increase existing position | demo_ready+ |
| close_position | 平倉 | Close entire position | shadow_ready+ |
| leverage_change | 調槓桿 | Change leverage setting | live_guarded_ready+ |
| borrow | 借款 | Borrow for margin trading | live_ready |
| transfer | 轉帳 | Transfer between accounts | Operator only |


## B. 保證金模式 / Margin Modes
- **Cross: **Shared margin across all positions in the account. Higher capital efficiency, but contagion risk.
- **Isolated: **Each position has its own margin. Loss limited to position margin. Recommended for initial deployment.
- **Portfolio: **Advanced mode using portfolio-level risk calculation. Requires deep understanding of Greeks and correlation.


## C. 持倉模式 / Position Modes
- **One-way: **Single position per symbol per side. Simpler to manage. Current default.
- **Hedge: **Simultaneous long and short positions on same symbol. Useful for hedging strategies. Planned for Delta-Neutral.

*End of Document** — DOC-04 Agent Capability Blueprint V2.0 — OpenClaw/Bybit*
