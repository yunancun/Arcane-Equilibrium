**EX-01**

Risk Control Boundary

風控邊界定義

OpenClaw / Bybit AI Agent Trading System

**Version 2.0**

2026-03-29

*Classification: Internal — Governance Document*


# 修訂歷史 / Revision History

| **Date** | **Ver** | **Author** | **Changes** |
|---|---|---|---|
| 2026-03-24 | 1.0 | Claude / Operator | Initial risk boundary definition |
| 2026-03-26 | 1.1 | Claude / Operator | Alignment with DOC-01 V1 |
| 2026-03-29 | 2.0 | Claude / Operator | Major expansion: P0/P1/P2 three-tier merge rules, Guardian dynamic adaptive boundaries, AI attention tax mechanism, adversarial stop design (hard/soft + concealment + ATR + anti-hunt), portfolio-level risk control |


# §1 用途與原則 / Purpose & Principles

This document defines the complete risk control framework for the OpenClaw/Bybit trading system. It specifies every risk parameter, its source of authority, and the rules governing how parameters interact across the three-tier priority system.

**核心原則：**Risk control is the Guardian Agent’s domain. The Guardian has override authority over all other Agents. No trade, no strategy, no system change may bypass risk controls.

**V2 擴展：**V1 僅定義基本風控參數。V2 新增：P0/P1/P2 三層合併規則、Guardian 動態自適應、AI 注意力稅風控機制、對抗性止損完整設計、組合層風控。


# §2 三層優先級風控體系 / Three-Tier Priority Risk Control

The risk framework operates on three tiers with strict priority ordering: P0 > P1 > P2. Higher-priority tiers always override lower-priority ones.


## §2.1 層級定義 / Tier Definitions

| **Tier** | **中文** | **Definition** | **Set By** | **Modifiable By** |
|---|---|---|---|---|
| **P0** | 品類專屬 | Product-family-specific hard limits. Set by Operator for each product family independently. Cannot be modified by any Agent. | Operator only | Operator only |
| **P1** | 全局硬上限 | System-wide hard limits that apply across all product families. Absolute defense line. | Operator only | Operator only |
| **P2** | Agent 自適應 | Agent-adjustable parameters that must stay within the effective boundary. Agent can tighten but never loosen beyond P0/P1. | Agent (Guardian) | Guardian Agent |


## §2.2 三層合併規則 / Three-Tier Merge Rule

**核心公式：**effective = min(P0 ?? P1, P1)

This formula means:
- **If P0 is set for this product family: **effective = min(P0, P1) — the stricter of the two applies
- **If P0 is not set (null): **effective = P1 — global limit applies as the fallback
- **P2 (Agent adaptive): **must stay within effective. Agent can tighten (lower max_position, tighter stops) but never loosen beyond effective


### 合併範例 / Merge Examples

| **Parameter** | **P1** | **P0** | **Effective** | **P2** | **Notes** |
|---|---|---|---|---|---|
| max_position_usd | $50,000 | $10,000 (spot) | min(10000, 50000) = $10,000 | $8,000 | Agent tightened within effective |
| max_position_usd | $50,000 | null (options) | $50,000 (P1 fallback) | $50,000 | P0 not set; P1 becomes effective |
| max_leverage | 10× | 3× (perp_linear) | min(3, 10) = 3× | 2× | Agent further reduced |
| max_daily_loss_pct | 5% | null | 5% (P1 fallback) | 3% | Agent tightened |
| hard_stop_pct | 8% | 5% (perp_linear) | min(5, 8) = 5% | 4% | Agent tightened stop |


## §2.3 風控參數完整清單 / Complete Risk Parameter List

| **Parameter** | **Description** | **P1** | **P0** | **P2** |
|---|---|---|---|---|
| max_position_usd | Maximum position size in USD equivalent | P1 | P0 per family | P2 can tighten |
| max_leverage | Maximum leverage multiplier | P1 | P0 per family | P2 can tighten |
| max_daily_loss_pct | Maximum daily loss as % of equity | P1 | — | P2 can tighten |
| max_daily_loss_usd | Maximum daily loss in absolute USD | P1 | — | P2 can tighten |
| hard_stop_pct | Hard stop-loss percentage per position | P1 | P0 per family | P2 can tighten |
| max_open_positions | Maximum concurrent open positions | P1 | P0 per family | P2 can tighten |
| max_drawdown_pct | Maximum portfolio drawdown | P1 | — | P2 can tighten |
| max_margin_utilization | Maximum margin usage as % of available | P1 | P0 per family | P2 can tighten |
| max_single_order_usd | Maximum single order size | P1 | P0 per family | P2 can tighten |
| consecutive_loss_pause | Pause after N consecutive losses | P1 (default 10) | — | P2 can tighten |
| max_correlated_exposure | Maximum exposure to correlated positions | P1 | — | P2 can tighten |
| funding_rate_threshold | Max acceptable funding rate for holding | — | — | P2 sets dynamically |


# §3 Guardian 動態自適應邊界 / Guardian Dynamic Adaptive Boundaries

The Guardian Agent dynamically adjusts P2 parameters based on real-time market conditions and system state. These adjustments are automatic, logged, and always within P0/P1 bounds.


## §3.1 自適應觸發條件 / Adaptive Trigger Conditions

| **Condition** | **Guardian Response** | **Rationale** |
|---|---|---|
| High volatility detected | Widen stops (1.5×), reduce position sizes (0.7×), increase margin buffer | Prevent stop-hunting in volatile markets |
| Squeeze regime detected | Tighten time stops (0.6×), reduce new entries | Avoid being trapped in low-momentum positions |
| Trending regime confirmed | Allow wider TP (1.3×), extend time stops (1.5×) | Let winners run in confirmed trends |
| Consecutive losses (< 10) | Progressively reduce position sizes | Gradual de-risking before auto-pause |
| Portfolio correlation > 0.7 | Block new correlated entries, flag for position reduction | Prevent concentration risk |
| Margin utilization > 70% | Block new entries, reduce-only mode | Preserve margin safety buffer |
| System health degraded | Pause new entries, maintain existing only | System health before market judgment |
| AI budget near ceiling | Downgrade compute tier, reduce scan frequency | Cost discipline |


## §3.2 自適應規則 / Adaptive Rules
- All adaptive changes are logged to audit trail with reason, old value, new value, and timestamp
- Adaptive changes are temporary: when trigger condition clears, parameters revert to baseline P2
- Adaptive changes can only tighten (never loosen) relative to current P2 baseline
- Multiple adaptive triggers stack: the most restrictive value wins
- Operator can override any adaptive change via Control API


# §4 對抗性止損設計 / Adversarial Stop-Loss Design

**設計哲學：**The market contains adversarial actors who profit from triggering clustered stop-loss orders. Our stop system must be invisible, adaptive, and unpredictable.


## §4.1 雙層止損架構 / Dual-Layer Stop Architecture


| **Type** | **中文** | **Description** | **Level Setting** | **Modifiability** |
|---|---|---|---|---|
| **Hard Stop** | 硬止損 | Absolute defense line. Triggered unconditionally when price reaches level. | P1 global ceiling (e.g., 8% max loss) | Never disabled, never loosened beyond P1 |
| **Soft Stop** | 軟止損 | Agent-evaluated conditional stop. Guardian assesses context before triggering. | ATR-based + regime-adjusted + random offset | Can be adjusted within hard stop boundary |


## §4.2 止損隱身 / Stop Concealment

**核心規則：**NEVER place stop orders on the exchange order book. All stops are monitored and triggered locally by the tick() function.
- Exchange stop orders are visible to market makers and can be hunted
- Local stops execute as market orders only when the trigger condition is met
- This means the Agent must maintain real-time price monitoring (WebSocket connection) at all times when positions are open
- **Fallback: **if WebSocket disconnects for > 30s, place emergency hard stop on exchange as safety net, remove when WS reconnects


## §4.3 反獵殺機制 / Anti-Hunt Mechanisms

| **Mechanism** | **Implementation** | **Purpose** |
|---|---|---|
| ATR-based dynamic stops | Stop distance scales with current volatility (Average True Range). Wider in volatile markets, tighter in calm markets. | Prevents fixed-percentage stops from being trivially hunted |
| Random offset | Small random offset (±0.1–0.3 ATR) added to calculated stop level. Different for each position. | Makes stop levels unpredictable to adversarial actors |
| Fake breakout detection | Before triggering soft stop, check: was this a wick/spike or sustained move? Check volume, multiple timeframes. | Avoids triggering on engineered wicks designed to sweep stops |
| Liquidity-aware exit | When closing a position, assess current order book depth. Split large closes into smaller chunks if liquidity is thin. | Prevents adverse price impact from large stop-triggered exits |
| Non-standard position sizes | Avoid round-number position sizes (e.g., exactly 1.0000 BTC). Use irregular quantities. | Reduces algorithmic footprint detection |
| Correlated asset validation | Before triggering soft stop, check if correlated assets show similar move. If isolated to one asset, may be manipulation. | Distinguishes market-wide moves from targeted manipulation |


## §4.4 Regime 感知止損調整 / Regime-Aware Stop Adjustment

Session 11 R1 implemented three-dimensional regime-aware multipliers:


| **Regime** | **Stop ×** | **TP ×** | **Time Stop ×** | **Rationale** |
|---|---|---|---|---|
| trending | 1.0× | 1.3× | 1.5× (~72h) | Let winners run; standard stops |
| ranging | 1.0× | 0.9× | 1.0× (~48h) | Standard parameters for mean-reversion |
| volatile | 1.5× | 0.8× | 0.8× (~38h) | Wider stops to avoid noise; take profits earlier |
| squeeze | 0.6× | 1.0× | 0.3× (~14h) | Tight time stops; expect breakout or exit quickly |
| unknown | — | — | — | No new entries allowed; existing positions use default |


# §5 AI 注意力稅風控機制 / AI Attention Tax Risk Mechanism

Every open position consumes AI monitoring resources. The attention tax mechanism ensures that positions whose monitoring cost exceeds their expected edge are identified and closed.


## §5.1 計算公式 / Calculation Formula

**cost_edge_ratio = total_holding_cost / initial_expected_edge**

Where total_holding_cost includes: funding fees, AI monitoring cost (per-tick evaluation), API call cost attributed to this position, and time-decay of edge.


## §5.2 等級制度 / Grade System

| **Grade** | **Ratio** | **Status** | **Action** |  |
|---|---|---|---|---|
| **A** | < 0.2 | **Healthy** | Position well within edge; continue holding |  |
| **B** | < 0.4 | **Acceptable** | Monitor; no action needed |  |
| **C** | < 0.6 | **Warning** | Guardian flags for review; consider tightening TP |  |
| **D** | < 0.8 | **Danger** | Guardian actively seeks exit opportunity |  |
| **F** | ≥ 0.8 | **Critical** | Auto-close triggered (if edge > taker close fee) |  |


## §5.3 保護機制 / Protection Mechanisms
- **免稅期 (Tax-free period): **First 30 minutes after position open are exempt. New positions need time to develop.
- **策略差異化閾值: **Grid strategies have higher thresholds (longer holding expected); scalp strategies have tighter thresholds.
- **平倉成本門檻 (Close cost gate): **Auto-close only triggers when edge_usd > notional × 0.00055 (taker fee). Prevents net-loss closes. (Session 12 F2)
- **Fill 碎片化修復: **Tail-quantity check reduces fills per order from 25–30 to ≤10, lowering attention tax burn rate. (Session 12 F1)


# §6 組合層風控 / Portfolio-Level Risk Control

Beyond individual position risk, the Guardian monitors aggregate portfolio risk across all dimensions.


## §6.1 相關性監控 / Correlation Monitoring
- **Pairwise correlation tracking: **compute rolling correlation between all open position pairs
- **Portfolio correlation threshold: **if average pairwise correlation > 0.7, block new entries in correlated instruments
- **Correlation breakdown: **during regime transitions, historically correlated assets may decouple; Guardian monitors for this
- **Sector exposure: **track concentration by category (DeFi, L1, meme, etc.)


## §6.2 資本分配風控 / Capital Allocation Risk
- **Maximum single-position allocation: **P1 cap (e.g., 20% of equity)
- **Maximum sector allocation: **P2 adaptive (e.g., 40% in any single sector)
- **Reserve buffer: **minimum 30% of equity must remain unallocated for margin calls and opportunities
- **Dynamic sizing: **position sizes scale with conviction score and inverse of current portfolio risk


## §6.3 組合級指標 / Portfolio-Level Metrics
- **Portfolio Sharpe ratio: **monitored continuously; degradation triggers Guardian review
- **Maximum drawdown: **P1 hard limit (e.g., 15% from peak)
- **Total margin utilization: **P1 ceiling; approaching limit triggers reduce-only mode
- **Value at Risk (VaR): **planned L2 capability for portfolio-level VaR estimation


# §7 熔斷器 / Circuit Breakers

Circuit breakers are automatic emergency controls that activate when extreme conditions are detected. They operate independently of the normal risk framework and cannot be disabled by Agent actions.


| **Circuit Breaker** | **Trigger Condition** | **Action** | **Priority** |
|---|---|---|---|
| Daily loss limit | Net daily loss exceeds P1 max_daily_loss | All new entries blocked; reduce-only mode until next UTC day | P1 |
| Portfolio drawdown | Equity drops > P1 max_drawdown_pct from peak | All trading halted; Operator notification | P1 |
| Consecutive losses | 10+ consecutive losing round-trips | Strategy auto-paused; other strategies continue | P1 |
| System health failure | Health gate fails (CPU/memory/network) | All new entries blocked; existing positions monitored on degraded schedule | P0 |
| Market data stale | All data sources STALE/EXPIRED for > 2 min | All trading halted; emergency stops activated | P0 |
| API connectivity loss | Cannot reach Bybit API for > 60s | Emergency hard stops placed on exchange; Operator alerted | P0 |


# §8 風控審計追蹤 / Risk Audit Trail

Every risk-related decision, parameter change, and circuit breaker activation is recorded in an immutable audit trail.


## §8.1 審計記錄內容 / Audit Record Contents
- Timestamp (UTC, millisecond precision)
- Event type (parameter_change, stop_trigger, circuit_breaker, adaptive_adjustment, manual_override)
- Actor (which Agent or Operator initiated the action)
- Old value and new value (for parameter changes)
- Reason / trigger condition
- Affected positions / strategies
- Market state at time of event (price, volume, regime)


## §8.2 審計保留 / Retention
- All audit records retained indefinitely (append-only log)
- Daily summary generated for operational review
- Accessible via GET /audit-summary and GUI Audit Trail tab


# §9 跨文件參照 / Cross-Reference


| **Document** | **中文** | **Relationship** |
|---|---|---|
| DOC-01 V2 | 憲法 | Root principles (especially #1 net PnL, #5 system health first, #6 fail-closed, #9 Agent max autonomy) |
| DOC-02 V2 | 邊界定義 | Execution boundary matrix; Operator vs Agent authority |
| DOC-04 V2 | 能力藍圖 | Capabilities G (autonomous trading) and H (adversarial awareness) constrained by this document |
| DOC-08 V1 | 實施橋樑 | Technical implementation of compute path budget gates |
| EX-05 V2 | 學習邊界 | Learning pipeline that feeds Analyst insights back into Guardian adaptations |
| EX-06 V1 | Multi-Agent | Guardian Agent role definition and override authority |
| EX-07 V1 | 感知平面 | Data freshness model used by health gates and circuit breakers |

*End of Document — EX-01 Risk Control Boundary V2.0 — OpenClaw/Bybit*
