---
name: Agent P2 dynamic SL/TP design
description: Agent P2 stop-loss and take-profit are ATR-dynamic by default (None). Agent can override with fixed value via agent_adjust() when it learns better strategies.
type: project
---

Agent P2 `effective_stop_loss_pct` and `effective_take_profit_pct` default to `None` (dynamic ATR-based mode).

**Why:** Hardcoded 2% SL caused 10:1 loss/win ratio — Grid Trading grid-step profit (~0.5%) was dwarfed by the 2% stop, making profitability mathematically impossible (needed 91% win rate to break even).

**How to apply:**
- `None` = dynamic mode: SL = max(ATR×2.0, 3%), TP = max(ATR×3.0, 4%), capped at P1 Operator limit
- When Agent learns a better stop strategy in the future, it can call `agent_adjust({"effective_stop_loss_pct": 5.0})` to override with a fixed value
- P1 `tp_enabled` controls whether TP fires at all — if Operator turns off TP in GUI, P2 TP value is irrelevant
- P1 `max_stop_loss_pct` (Operator GUI) is always the hard ceiling — Agent P2 can never exceed it
