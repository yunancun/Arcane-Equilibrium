**DOC-06**

Change Governance

變更治理

OpenClaw / Bybit AI Agent Trading System

**Version 2.0  —  2026-03-29**

*Classification: Internal — Governance Document*


# 修訂歷史 / Revision History

| **Date** | **Ver** | **Author** | **Changes** |
|---|---|---|---|
| 2026-03-24 | 1.0 | Claude / Operator | Initial change governance framework |
| 2026-03-26 | 1.1 | Claude / Operator | Minor alignment |
| 2026-03-29 | 2.0 | Claude / Operator | Major rewrite: expanded AI autonomous scope, Agent self-adjustment L1 auto-effective, AI budget upgrade as empowerment flow, Paper→Live gate conditions, three-tier change classification (green/yellow/red) |


# §1 用途 / Purpose

This document governs how the system changes over time: which changes the Agent can make autonomously, which require Operator approval, and which are forbidden entirely.

**V2 關鍵變更：**V1 將大部分變更定義為需要 Operator 批准。V2 大幅擴大 AI 自主範圍，反映「Agent 最大自主權」原則。同時引入三色分類法（綠/黃/紅）讓邊界更清晰。


# §2 三色變更分類 / Three-Color Change Classification

Every system change falls into one of three categories, color-coded for clarity:


| **Color** | **中文** | **Definition** |
|---|---|---|
| **🟢 GREEN** | 自動生效 | Agent can make this change autonomously. Logged to audit trail. No Operator approval needed. |
| **🟡 YELLOW** | 需要審批 | Agent proposes the change. Requires explicit Operator approval before taking effect. |
| **🔴 RED** | 僅 Operator | Only the Operator can initiate and execute this change. Agent cannot even propose it. |


# §3 完整變更路由表 / Complete Change Routing Table

The following table is the authoritative reference for change governance. When in doubt, consult this table.


## §3.1 策略與交易變更 / Strategy & Trading Changes

| **Change** | **Color** | **Details** |
|---|---|---|
| Deploy new strategy to Paper | **🟢 GREEN** | Analyst auto-deploys from incubation pipeline |
| Adjust P2 adaptive parameters | **🟢 GREEN** | Within effective = min(P0??P1, P1); auto-logged |
| Pause underperforming strategy | **🟢 GREEN** | 10 consecutive losses trigger auto-pause |
| Retire a strategy from paper | **🟢 GREEN** | Analyst removes based on performance data |
| Adjust strategy parameters in paper | **🟢 GREEN** | Free experimentation in paper environment |
| Promote strategy paper→live (known type) | **🟢 GREEN** | Auto if ALL gate criteria met simultaneously |
| Promote strategy paper→live (new type) | **🟡 YELLOW** | First-ever deployment of new type needs Operator approval |
| Override consecutive-loss auto-pause | **🟡 YELLOW** | Operator must explicitly re-enable |
| Add new instrument to trading universe | **🟢 GREEN** | Scanner auto-discovers from 650+ symbols |
| Enable new product family | **🔴 RED** | Operator only; requires P0 config and risk review |


## §3.2 風控變更 / Risk Control Changes

| **Change** | **Color** | **Details** |
|---|---|---|
| Guardian adaptive tightening (P2) | **🟢 GREEN** | Auto based on market conditions; reverts when condition clears |
| Adjust AI attention tax thresholds | **🟢 GREEN** | Analyst proposes, Guardian applies within bounds |
| Modify P1 global hard limits | **🔴 RED** | Operator only; system-wide safety boundary |
| Modify P0 product-family limits | **🔴 RED** | Operator only; product-specific safety boundary |
| Change max_daily_loss ceiling | **🔴 RED** | Operator only |
| Change max_drawdown ceiling | **🔴 RED** | Operator only |
| Disable a circuit breaker | **🔴 RED** | Operator only; circuit breakers are non-negotiable |


## §3.3 AI 計算變更 / AI Compute Changes

| **Change** | **Color** | **Details** |
|---|---|---|
| Auto-downgrade compute tier (budget pressure) | **🟢 GREEN** | Agent auto-downgrades when approaching budget ceiling |
| Allocate budget across L1/L1.5/L2 | **🟢 GREEN** | Agent optimizes allocation within daily ceiling |
| Activate L1.5 tier (first time) | **🟢 GREEN** | Auto when positive net PnL sustained 2+ weeks |
| Activate L2 tier (first time) | **🟢 GREEN** | Auto when L1.5 demonstrates positive AI ROI |
| Increase daily AI budget ceiling | **🟡 YELLOW** | Operator approval; Agent may propose with ROI justification |
| Add new AI provider | **🔴 RED** | Operator only; requires API key and cost configuration |


## §3.4 系統變更 / System Changes

| **Change** | **Color** | **Details** |
|---|---|---|
| Change system_mode (read_only/paper/demo/live) | **🔴 RED** | Operator only; fundamental system state |
| Grant/revoke execution_authority | **🔴 RED** | Operator only |
| Modify governance documents (DOC-01 through DOC-NAV) | **🔴 RED** | Operator only; constitutional changes |
| Deploy code changes to production | **🔴 RED** | Operator only; Agent cannot self-modify |
| Modify API security configuration | **🔴 RED** | Operator only |
| Restart/stop system services | **🔴 RED** | Operator only (systemd auto-restart is infrastructure, not Agent action) |


## §3.5 學習變更 / Learning Changes

| **Change** | **Color** | **Details** |
|---|---|---|
| Record observations | **🟢 GREEN** | Fully automatic; append-only |
| Extract lessons from observations | **🟢 GREEN** | Auto-scan enabled |
| Generate hypotheses | **🟢 GREEN** | Analyst L2+ can auto-generate |
| Run experiments in paper | **🟢 GREEN** | No pre-approval needed |
| Propose verdict on hypothesis | **🟢 GREEN** | Analyst proposes; high-impact go to review queue |
| Modify Paper→Live gate criteria | **🔴 RED** | Operator only; fundamental safety gate |
| L5 meta-learning pipeline changes | **🟡 YELLOW** | Analyst proposes; Operator must approve |
| Delete historical learning data | **🔴 RED** | Forbidden; learning data is append-only |


# §4 Paper → Live 閘門條件 / Paper-to-Live Gate Conditions

The Paper→Live gate is the most critical change governance mechanism. It controls when the system transitions from paper trading to live execution.


## §4.1 闘門條件 / Gate Criteria (ALL must be met simultaneously)
- **Duration: **≥ 4 weeks of continuous paper trading
- **Trade count: **≥ 500 completed round-trip trades
- **Net PnL: **Positive after all costs (fees + AI + slippage)
- **Win rate: **> 30% (trades closed at profit / total trades)
- **Sharpe ratio: **> 0.5 (annualized, risk-adjusted)


## §4.2 闘門評估規則 / Gate Evaluation Rules
- Evaluation is automatic: Guardian checks criteria daily
- All 5 criteria must be met simultaneously on the same evaluation day
- Criteria are evaluated per-strategy-type, not system-wide
- Gate criteria themselves are RED (Operator-only to modify)
- If a strategy passes the gate, it becomes live-eligible but does not auto-start live trading until system_mode allows


# §5 變更審計 / Change Audit Requirements

Every change, regardless of color, must be recorded in the audit trail.


## §5.1 審計記錄必含欄位 / Required Audit Fields
- Change ID (unique, sequential)
- Timestamp (UTC, millisecond)
- Change type and color classification
- Initiator (which Agent, or Operator)
- Target (parameter, strategy, system component)
- Old value → New value
- Reason / trigger condition
- Approval status (auto-approved for GREEN, pending/approved/rejected for YELLOW)


## §5.2 審計可見性 / Audit Visibility
- All changes visible in GUI Audit Trail tab
- GREEN changes: real-time display, no notification
- YELLOW changes: pending status highlighted until Operator reviews
- RED changes: logged when Operator executes, full before/after state


# §6 放權流程 / Empowerment Flow

**核心理念：**權限按表現贏得（根原則 #4）。以下是 Agent 如何逐步獲得更高自主權的流程。


| **#** | **Milestone** | **Trigger** | **New Capability** | **Approval** |
|---|---|---|---|---|
| 1 | Paper Trading starts | System launch | Agent can trade in paper; L0+L1 compute | Automatic |
| 2 | L1.5 cloud unlocked | Positive net PnL for 2+ weeks | Haiku + Perplexity search enabled | Automatic (GREEN) |
| 3 | L2 cloud unlocked | L1.5 demonstrates positive AI ROI | Sonnet/Opus enabled for high-value decisions | Automatic (GREEN) |
| 4 | Strategy auto-promotion | Paper→Live gate criteria met | Validated strategies become live-eligible | Automatic (GREEN) |
| 5 | Supervised Live (M chapter) | system_mode changed to live | Live trading with strict monitoring | Operator (RED) |
| 6 | Autonomous Live (N chapter) | Sustained positive live performance | Full autonomous execution within P0/P1 | Operator (RED) |


# §7 跨文件參照 / Cross-Reference


| **Document** | **中文** | **Relationship** |
|---|---|---|
| DOC-01 V2 | 憲法 | Root Principles #4 (權限按表現贏得) and #7 (學習≠自作主張) |
| DOC-02 V2 | 邊界定義 | Operator vs Agent authority boundary; execution boundary matrix |
| DOC-04 V2 | 能力藍圖 | Capabilities that evolve through this change governance framework |
| EX-01 V2 | 風控邊界 | P0/P1/P2 parameters governed by RED/YELLOW/GREEN rules here |
| EX-05 V2 | 學習邊界 | Learning-driven changes routed through this governance framework |
| EX-06 V1 | Multi-Agent | Agent roles that determine who can initiate which changes |

*End of Document — DOC-06 Change Governance V2.0 — OpenClaw/Bybit*
