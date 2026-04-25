**DOC-02**

Boundary Definition

邊界定義

OpenClaw / Bybit AI Agent Trading System

**Version 2.0**

2026-03-29

*Classification: Internal — Governance Document*


# 修訂歷史 / Revision History

| **Date** | **Ver** | **Author** | **Changes** |
|---|---|---|---|
| 2026-03-24 | 1.0 | Claude / Operator | Initial boundary definition (H0–H5 + I as prompt roles) |
| 2026-03-26 | 1.1 | Claude / Operator | Minor alignment with DOC-01 V1 |
| 2026-03-29 | 2.0 | Claude / Operator | Major rewrite: H1–H5 reframed as Multi-Agent precursors; AI tool usage boundaries; L0/L1/L2 proactive scan triggers; execution boundary matrix; product family boundary map |


# §1 用途與範圍 / Purpose & Scope

This document defines the boundaries within which the OpenClaw/Bybit AI Agent operates. It answers: Where can the Agent act? Where must it stop and defer to the Operator? Where does each governance layer begin and end?

**V2 重大變更：** V1 將 H1–H5 定義為 5 個 prompt 角色（thought gate / budget gate / model router / governor / cost logger）。V2 將其重構為 Multi-Agent 治理的前身，明確每個治理層如何映射到 EX-06 定義的 5 個 Agent 角色。同時新增 AI 工具使用邊界、L0/L1/L2 主動掃描觸發邏輯、執行邊界矩陣、產品族邊界圖。

**與其他文件關係：** DOC-01 憲法定義「為什麼」；DOC-04 能力藍圖定義「能做什麼」；本文件定義「在哪裡做」——即邊界、分區、權限分界線。


# §2 治理層邊界 / Governance Layer Boundaries

The system’s governance is organized into distinct layers, each with clear entry conditions, responsibilities, and handoff rules.


## §2.1 H0 — 本地確定性判斷內核 / Local Deterministic Judgment Core

**定位：**所有決策的第一道關卡。零成本、最低延遲、純本地執行。不涉及任何 AI 推理。

**Multi-Agent 映射：**Guardian Agent 的硬性檢查層。

### 檢查項目 / Checks
- **Freshness gate: **market data must be FRESH or RECENT (not STALE/EXPIRED)
- **Health gate: **system health must pass (CPU, memory, network, disk)
- **Eligibility gate: **instrument must be in authorized product family at required capability level
- **Risk envelope: **position size, leverage, margin utilization within P0/P1 hard limits
- **Cooldown gate: **consecutive-loss auto-pause not active for this strategy

### 邊界規則 / Boundary Rules
- H0 is non-bypassable: every decision must pass H0 before reaching any higher layer
- H0 failures are immediate rejections: no escalation to AI layers
- H0 runs in < 1ms: pure in-memory computation, no external calls
- H0 can only say NO (reject) or PASS (forward to next layer); it never generates trading ideas


## §2.2 H1–H5 — AI 治理層（Multi-Agent 前身）/ AI Governance Layer (Multi-Agent Precursors)

**V2 重構說明：**V1 將 H1–H5 定義為 5 個獨立的 prompt 角色。在實際工程中，它們演變為結構化的治理管線階段。V2 明確它們是 Multi-Agent 架構（EX-06）的治理前身，每個 H 層映射到特定的 Agent 职責。


| **ID** | **Name** | **中文** | **Agent** | **Responsibility** | **Input** | **Output** |
|---|---|---|---|---|---|---|
| H1 | Thought Gate | 思維門 | Strategist | Determines if a market observation warrants deeper analysis. Filters noise from signal. Controls when AI resources are invoked. | Observation → “Is this worth analyzing?” | If YES → H2; if NO → discard |
| H2 | Budget Gate | 預算門 | Guardian | Checks if AI budget allows the proposed computation tier. Prevents cost overruns. Enforces zero-cost-runnable principle. | H1 approval + proposed tier | If budget allows → H3; if not → downgrade tier or reject |
| H3 | Model Router | 模型路由 | Strategist | Routes the analysis request to the optimal compute tier (L0/L1/L1.5/L2) based on complexity, cost, and time constraints. | H2 approved budget + query complexity | Routed request → H4 |
| H4 | Governor | 治理器 | Guardian | Final governance check before Decision Lease emission. Validates the AI’s recommendation against risk framework, position limits, and market conditions. | AI analysis result | If valid → H5; if rejected → log + discard |
| H5 | Cost Logger | 成本記錄 | Analyst | Records the full cost of the governance pipeline execution. Attributes AI cost to the resulting position for attention tax calculation. | Completed governance cycle | Cost record → I (Decision Lease) |


### 過渡時期的實際狀態 / Current Transitional State

As of Session 12, the H1–H5 governance modules exist as code (*thought_gate.py, budget_gate.py, model_router.py, governor.py, cost_logger.py*) but the main trading pipeline bypasses them (Capability C = 30%). The pipeline currently runs: H0 → direct strategy signal → Paper Engine. Full AI governance integration is gated on win_rate > 20%.


## §2.3 I — Decision Lease 影子控制平面 / Decision Lease Shadow Control Plane

**定位：**H5 輸出的治理決定不是即時命令——它們是有時效、可撤銷的 Decision Lease。這是「IAI 輸出不能當即時命令」（根原則 #3）的工程實現。

**Multi-Agent 映射：**Strategist Agent 簽發 lease，Executor Agent 消費 lease。Guardian Agent 可隨時撤銷。

### Lease 屬性 / Lease Properties
- **TTL (Time-to-Live): **lease expires automatically after configured duration
- **Revocability: **Guardian or Operator can revoke any active lease at any time
- **Idempotency: **each lease has a unique ID; double-execution is prevented
- **Audit trail: **every lease emission, execution, expiry, and revocation is logged

### 邊界規則 / Boundary Rules
- Executor can ONLY act on a valid, non-expired, non-revoked lease
- Executor cannot generate its own leases
- A lease authorizes a specific action on a specific instrument with specific parameters—no generalization
- Current state: shadow-only (lease is logged but not connected to live execution)


# §3 計算路徑觸發邊界 / Compute Path Trigger Boundaries

**V2 關鍵變更：**V1 將計算路徑描述為被動審查（等待交易提案後才判斷用哪個層級）。V2 重構為主動掃描模式：Agent 主動掃描市場機會，根據發現的複雜度在不同計算層級間路由。


## §3.1 主動掃描 vs 被動審查 / Proactive Scan vs Passive Review

| **Dimension** | **V1: Passive Review** | **V2: Proactive Scan** |
|---|---|---|
| Trigger | Wait for trade proposal, then decide compute tier | Continuously scan market; compute tier selected based on opportunity complexity |
| Initiative | Reactive: AI only engaged when asked | Proactive: Scout Agent scans 650+ symbols every 5 min |
| Routing | Single-path: all proposals go through same pipeline | Multi-path: simple signals stay L0; complex patterns escalate to L1/L2 |
| Cost | Cost determined after analysis begins | Budget gate (H2) approves tier BEFORE computation starts |


## §3.2 層級觸發矩陣 / Tier Trigger Matrix

Each compute tier has explicit trigger conditions. The Agent selects the lowest-cost tier capable of handling the task.


| **Tier** | **中文** | **Cost/call** | **Latency** | **Trigger Conditions** | **Constraints** |
|---|---|---|---|---|---|
| L0 | 本地確定性 | 0 | < 1ms | Freshness check, health gate, risk envelope, eligibility, MA crossover signal (simple), grid level calculation, stop/TP evaluation, cooldown check | Always runs first |
| L1 | 本地 Ollama | 0 (local) | < 3s | Regime detection, multi-indicator pattern recognition, unusual volume analysis, correlation screening, strategy parameter suggestion | Qwen2.5 7B, 12GB limit, CPUQuota=150% |
| L1.5 | 低成本雲端 | $0.01–0.05 | 2–5s | Market commentary parsing, news sentiment extraction, cross-source fact checking, event impact assessment | Haiku + Perplexity; requires positive PnL gate |
| L2 | 完整雲端 | $0.05–0.50 | 5–15s | Complex multi-factor strategy evaluation, regime transition prediction, portfolio rebalancing decisions, hypothesis evaluation, meta-learning | Sonnet/Opus; requires positive AI ROI gate |


## §3.3 四層搜索降級 / Four-Layer Search Degradation

Information retrieval follows a degradation chain, always starting from the cheapest source:
- **L0 Cache: **local in-memory cache of recent market data, indicator values, and previous analysis results
- **L1 Local: **Ollama inference on locally stored data (K-lines, order book snapshots)
- **L1.5 Perplexity: **low-cost web search for news, sentiment, and event verification
- **L2 Full Search: **comprehensive cloud-based analysis combining multiple data sources


# §4 AI 工具使用邊界 / AI Tool Usage Boundaries

**V2 新增章節：**V1 未明確定義 AI 可以使用哪些工具、在什麼條件下使用。V2 建立完整的 AI 工具使用邊界矩陣。


## §4.1 允許的 AI 工具 / Permitted AI Tools

| **Tool** | **Tier** | **Agents** | **Permitted Use** | **Constraints** |
|---|---|---|---|---|
| Local Ollama inference | L1 | Strategist, Analyst | Regime detection, pattern recognition, hypothesis evaluation | 3s timeout, 12GB memory cap |
| Haiku API | L1.5 | Strategist, Analyst | Market commentary, news parsing, sentiment scoring | Budget gate required, $0.01–0.03/call |
| Perplexity Search | L1.5 | Scout | News search, event verification, market intelligence | Budget gate required, ~$0.005/search |
| Sonnet/Opus API | L2 | Strategist, Analyst | Complex analysis, strategy evolution, meta-learning | Budget + ROI gate, $0.05–0.50/call |
| OpenClaw web-pilot | L1.5 | Scout | Web scraping for crypto news, exchange announcements | Rate-limited, non-trading-critical only |
| OpenClaw Memory | L0 | Analyst | Store and retrieve accumulated market knowledge | Local, zero cost |
| OpenClaw Cron | L0 | All Agents | Scheduled tasks: scanning, reporting, health checks | Local, zero cost |


## §4.2 禁止的 AI 行為 / Prohibited AI Behaviors
- AI cannot modify its own code, configuration files, or deployment settings
- AI cannot access or modify Operator credentials, API keys, or security tokens
- AI cannot initiate fund transfers, withdrawals, or account-level operations
- AI cannot communicate externally (email, messaging) without Operator-configured channels
- AI cannot disable or weaken any P0/P1 risk control
- AI cannot override the consecutive-loss auto-pause without Operator approval
- AI cannot access data outside its designated Agent role (see EX-06 data access matrix)


## §4.3 條件性允許 / Conditional Permissions

These actions are permitted only when specific conditions are met:
- **L1.5/L2 activation: **requires positive net PnL sustained for 2+ weeks
- **New strategy live deployment: **requires Paper→Live gate criteria (4 weeks, 500 trades, Sharpe > 0.5)
- **Product family expansion: **requires Operator explicit authorization per family
- **P2 adaptive parameter changes: **auto-effective within P0/P1 bounds, logged for audit
- **Cross-strategy transfer learning: **requires Analyst L3+ capability level


# §5 執行邊界矩陣 / Execution Boundary Matrix

This matrix defines what each system role can and cannot do across key operational dimensions.


| **Action** | **Operator** | **Executor** | **Guardian** | **Analyst** | **Scout** | **Strategist** |
|---|---|---|---|---|---|---|
| Place/cancel/amend orders | ✔ | ✔ (within lease) | ✔ (P0/P1 enforcement) | ✘ | ✔ (data collection) | ✘ |
| Modify P2 adaptive params | ✔ | ✘ | ✔ (within P0/P1) | ✔ (propose only) | ✘ | ✘ |
| Modify P0/P1 hard limits | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ |
| Enable product family | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ |
| Change system_mode | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ |
| Deploy new strategy (paper) | ✔ | ✘ | ✘ | ✔ (propose) | ✔ (scan) | ✘ |
| Promote strategy to live | ✔ (or auto if gate met) | ✘ | ✔ (verify gate) | ✔ (evaluate) | ✘ | ✘ |
| Write observations/lessons | ✘ | ✘ | ✘ | ✔ | ✔ (raw data) | ✘ |
| AI consultation (L1.5/L2) | ✔ | ✘ | ✘ | ✔ (if budget) | ✘ | ✔ |
| Fund transfer/withdrawal | ✔ (manual only) | ✘ | ✘ | ✘ | ✘ | ✘ |


# §6 產品族邊界圖 / Product Family Boundary Map

Each product family has independent boundaries for capability level, risk parameters, and execution permissions. Product families progress independently through capability levels.


| **Family** | **Current Level** | **P0 Config** | **Leverage Range** | **Trading** | **Notes** |
|---|---|---|---|---|---|
| spot | observe_only | None | None | ✘ | Lowest risk; first candidate for shadow_ready promotion |
| margin | unsupported | N/A | N/A | ✘ | Requires borrowing logic; deferred |
| perp_linear | shadow_ready | Independent P0 | 1–125× (P1 cap) | ✔ (paper) | Primary arena; most mature implementation |
| perp_inverse | unsupported | N/A | N/A | ✘ | Coin-settled adds currency risk; deferred |
| options | unsupported | N/A | N/A | ✘ | Greeks risk; requires specialized Guardian logic |
| other_deriv | unsupported | N/A | N/A | ✘ | Expiry management needed; reserved |


## §6.1 產品族升級邊界 / Product Family Promotion Boundaries

Promotion from one capability level to the next requires:
- **unsupported → observe_only: **Operator explicit authorization + data feed integration verified
- **observe_only → shadow_ready: **H0 checks implemented + risk parameters configured + 1 week data observation
- **shadow_ready → demo_ready: **Paper Trading gate passed (4 weeks, 500 trades, positive PnL, Sharpe > 0.5)
- **demo_ready → live_guarded_ready: **Demo (Bybit sandbox) results verified + Operator explicit approval
- **live_guarded_ready → live_ready: **Sustained positive live performance + Guardian audit clean + Operator explicit approval


# §7 Operator vs Agent 權限分界 / Authority Boundary

The core design philosophy: maximize Agent autonomy within hard safety boundaries. The Operator sets the playing field; the Agent plays the game.


## §7.1 Operator 專屬權限 / Operator-Only Authority
- Set and modify P0/P1 hard risk limits
- Enable/disable product families
- Change system_mode (read_only / paper / demo / live)
- Grant/revoke execution_authority
- Approve first-ever live deployment of new strategy type
- Fund transfers, withdrawals, account-level operations
- Override consecutive-loss auto-pause
- Modify the governance document set (DOC-01 through DOC-NAV)


## §7.2 Agent 自主權限 / Agent Autonomous Authority
- Select trading instruments from authorized product families
- Choose strategy type based on market conditions
- Set and adjust strategy parameters (within P0/P1 bounds)
- Determine position sizes (within P1 max position limit)
- Decide entry and exit timing
- Adjust P2 adaptive risk parameters (within effective = min(P0 ?? P1, P1))
- Deploy new strategies to Paper Trading without Operator approval
- Auto-promote strategies from paper to live when gate criteria met
- Pause/retire underperforming strategies
- Allocate AI compute budget across tiers (within daily ceiling)
- Write observations, lessons, hypotheses to learning pipeline


## §7.3 灰色區域 / Grey Zone (Requires Escalation Protocol)

Some actions fall in a boundary zone where the Agent should attempt but escalate if uncertain:
- **Unusual market conditions: **If regime detection confidence < 50%, Agent should reduce exposure rather than seek Operator input (fail-closed, Root Principle #6)
- **Correlated position buildup: **If portfolio pairwise correlation > 0.7, Agent should reduce before escalating
- **AI budget spike: **If daily AI spend approaches 80% of ceiling before midday, Agent auto-downgrades tier


# §8 數據邊界 / Data Boundaries

Each Agent has defined data access rights. No Agent may access data outside its designated scope (see EX-07 Data Plane for full specification).


| **Agent** | **Can Access** | **Cannot Access** |
|---|---|---|
| Scout | Market data (all sources), news feeds, event calendars, exchange announcements | Trade execution data, learning pipeline, risk configuration |
| Strategist | Market data, indicator values, signal outputs, learning insights, portfolio state | Raw Operator credentials, fund balances, account settings |
| Guardian | All system state (full read access for risk enforcement) | Cannot write to learning pipeline; read-only on all data |
| Analyst | Trade history, round-trip records, observations, lessons, hypotheses, experiments | Cannot read live order book in real-time (latency-sensitive data reserved for Scout) |
| Executor | Active Decision Leases, current positions, order status | Cannot read strategy logic, market analysis, or learning data |


# §9 時間邊界 / Temporal Boundaries

The system operates with explicit time boundaries that constrain Agent behavior.


## §9.1 延遲預算 / Latency Budget

| **Operation** | **Budget** | **Notes** |
|---|---|---|
| H0 check | < 1ms | Non-negotiable; pure in-memory |
| L1 Ollama inference | < 3s | Hard timeout; fallback to L0 on timeout |
| L1.5 cloud call | 2–5s | Soft timeout; retry once, then fallback to L1 |
| L2 cloud call | 5–15s | Acceptable for non-time-critical decisions |
| Market data freshness | < 5s for FRESH | STALE > 30s triggers degradation; EXPIRED > 120s blocks trading |
| Decision Lease TTL | Configurable (default 60s) | Expired leases are not executable |
| Paper Engine tick | ~100ms per symbol | Tighter for live (planned < 10ms) |


## §9.2 冷却期 / Cooldown Boundaries
- **Strategy consecutive-loss pause: **10 consecutive losses → auto-pause; Operator or time-based cooldown to resume
- **AI budget reset: **daily budget resets at UTC 00:00
- **Scanner cycle: **5-minute minimum interval between full market scans
- **Learning review cadence: **hypotheses accumulate; Operator reviews on their schedule (no forced cadence)


# §10 跨文件參照 / Cross-Reference


| **Document** | **中文** | **Relationship to DOC-02** |
|---|---|---|
| DOC-01 V2 | 憲法 | Root principles that this document’s boundaries enforce |
| DOC-04 V2 | 能力藍圖 | Capabilities that operate within these boundaries |
| DOC-06 V2 | 變更治理 | How boundaries themselves change over time |
| DOC-08 V1 | 實施橋樑 | Technical implementation of compute path boundaries |
| EX-01 V2 | 風控邊界 | P0/P1/P2 risk parameters referenced throughout this document |
| EX-06 V1 | Multi-Agent | Agent roles and communication boundaries referenced in §2 and §5 |
| EX-07 V1 | 感知平面 | Data boundaries referenced in §8 |

*End of Document** — DOC-02 Boundary Definition V2.0 — OpenClaw/Bybit*
