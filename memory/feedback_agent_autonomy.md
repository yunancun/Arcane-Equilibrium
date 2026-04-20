---
name: Agent Autonomy Preference
description: User wants maximum agent trading autonomy — user sets only global caps, agent decides everything else (strategy, parameters, timing)
type: feedback
---

User wants the agent to make strong autonomous trading decisions. User only sets global-level stop-loss/take-profit. Agent should decide:
- Which strategy to use (funding rate, bollinger, grid, AI-driven)
- When to activate/deactivate strategies
- Whether accumulated data is sufficient to start a strategy
- Parameter tuning (grid spacing, BB periods, RSI thresholds, etc.)
- Position sizing based on confidence/volatility

**Why:** User explicitly stated "用户应该只会在global层面设置一个止盈止损，剩下的怎麼交易，交易什麼，那種交易邏輯都希望agent能夠自己決定，而我希望agent能做出很強的決定"

**How to apply:** When designing risk control and strategy systems, always include agent-adjustable parameters within user-defined hard caps. Never require user to configure per-strategy details. Agent must have autonomy to decide data sufficiency, parameter values, and strategy activation.
