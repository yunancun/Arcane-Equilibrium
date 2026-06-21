# 2026-06-21 -- Cost gate reject counterfactual learning loop

Demo is healthy but mostly blocked by cost gate. Recent market data continues accumulating; execution/fill samples are not.

New read-only audit:

- `/tmp/openclaw/cost_gate_counterfactual/cost_gate_reject_counterfactual_latest.md`
- sha256 `9acc5a3c54bd77c644d0a8d9ce2aeab3cd36a7b6075c1a8212122130a69bcac0`

Key result: cost-gate rejects are not fully silent, but the learning chain is incomplete. They enter `risk_verdicts` and `learning.decision_features`, but not `trading.intents`; `decision_outcomes` coverage is currently zero for the audited rejects due to backlog/sparse context coverage.

Operational read: do not globally lower cost gate. Build a bounded demo-learning lane: tiny exploration budget, side-cell targeting, durable outcome labels, and automatic edge-estimate feedback. BTC Buy rejects look correctly blocked; ETH/NEAR Sell rejects show learnable missed opportunity.
