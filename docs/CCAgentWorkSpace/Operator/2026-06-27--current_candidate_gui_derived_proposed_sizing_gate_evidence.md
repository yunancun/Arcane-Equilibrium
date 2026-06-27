# Operator Note: GUI-Derived Proposed-Sizing Gate Evidence

State transition: `BLOCKED_BY_LOSS_CONTROL`.

The `cap_usdt=10` interpretation is not used as global risk authority. Current code and evidence now require GUI-backed Rust RiskConfig:

- GUI `P1 Risk/Trade=10.0%` -> `per_trade_risk_pct=0.1`
- Accepted Demo equity `9552.43426257` -> GUI per-trade cap `955.24342626 USDT`
- GUI `Max Single Position=25%` -> max-single-position budget `2388.10856564 USDT`
- Effective single-order cap -> `min(955.24342626, 2388.10856564, Guardian adjusted cap)`

With Guardian still `CAUTIOUS` at multiplier `0.7`, the effective cap is `668.67039838 USDT`. The reviewed no-order proposed shape is `102.0 AVAX / 668.304 USDT`, below GUI per-trade cap, GUI max-single-position budget, and Guardian-adjusted cap.

Runtime remains blocked: Decision Lease live count is `0`, and Guardian risk state is not `NORMAL`. No order/probe/live authority was granted and no order was submitted.

Key artifacts:

- Proposal: `/tmp/openclaw/current_candidate_guardian_adjusted_sizing_proposal_20260627T053254Z/current_candidate_guardian_adjusted_sizing_proposal.json`
- Final gate packet: `/tmp/openclaw/current_candidate_proposed_sizing_decision_lease_guardian_gate_20260627T053314Z/current_candidate_proposed_sizing_decision_lease_guardian_gate_evidence.json`
- Session state: `/tmp/openclaw/session_loop_state_20260627T053455Z_gui_derived_proposed_sizing_gate_evidence.json`

Next: wait for or validate a real current-candidate Demo Decision Lease and Guardian `NORMAL`/valid proposed-sizing gate before fresh actual-admission BBO. Do not use the reduced gate to clear the old larger order shape.
