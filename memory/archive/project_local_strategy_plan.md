---
name: Full-Category Risk Framework and Agent Autonomy Plan
description: 2026-03-27 comprehensive design - 3-tier risk (P0/P1/P2) + Bybit V5 all 6 categories + adversarial stops + AI attention tax + agent autonomous trading
type: project
---

Comprehensive risk framework design completed 2026-03-27. Key elements:

1. **3-tier priority risk:** P0 category-specific (user) > P1 global (user) > P2 agent-adaptive (agent). P0 can only be stricter than P1. Agent P2 can only tighten within effective cap.
2. **Bybit V5 full coverage:** 6 product categories (spot/margin/linear/inverse/futures/options) + 10+ order types (market/limit/conditional/TP-SL/trailing/reduce-only/iceberg/TWAP/batch).
3. **Adversarial stop logic:** Hard stop (absolute, invisible to exchange) + Soft stop (agent evaluates: fake breakout detection, liquidity-aware exit, time-aware). Anti-hunting: ATR + random offset, non-standard sizing, iceberg/TWAP.
4. **AI attention tax:** Position real cost = financial + AI monitoring. cost_edge_ratio tracks efficiency. Natural decay pressure on positions.
5. **Agent autonomy:** Agent decides what/when/how to trade. User only sets global caps.

**Why:** User wants agent to "squeeze every drop" of Bybit API potential while maintaining robust risk control against HFT bots and AI trading opponents.

**How to apply:** Design doc at `docs/references/2026-03-27--phase1_risk_framework_and_agent_autonomy_design.md`. Audit at `docs/references/2026-03-27--local_trading_logic_audit_and_strategy_plan.md`. Phase 1 (security + risk framework) must come first.
