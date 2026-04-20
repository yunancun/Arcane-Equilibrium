---
name: Risk parameter changes must be scoped
description: When adjusting SL/TP/trailing code, only change what was asked — never reset other risk settings. GUI-adjustable params must stay visible in GUI.
type: feedback
---

When modifying stop-loss, take-profit, or trailing stop related code, ONLY change the specific part requested. Do NOT reset or override other risk parameters as a side effect.

**Why:** In a previous session, changing SL defaults also flipped tp_enabled from False to True and left trailing_stop_enabled at False — undoing the user's intended configuration. This caused the profit-side exit mechanism to be completely wrong.

**How to apply:**
- Before changing any risk parameter, read the current runtime config (API + paper state) to understand the full picture
- Only modify the specific parameter(s) requested
- If a parameter is GUI-adjustable (P1 GlobalRiskConfig or P2 AgentRiskParams), ensure the change is reflected in both: (1) code defaults, (2) API response via to_dict(), (3) GUI display (tab-risk.html)
- After making changes, verify ALL risk params are unchanged except the one(s) modified
- Never assume what the user wants for unrelated parameters — ask if unclear
