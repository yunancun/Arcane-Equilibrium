# AgentTodo MAG-042 PositionReview V2 Operator Report

Date: 2026-05-07
Status: DONE

Completed MAG-042.

What changed:

- Added a typed PositionReview contract.
- Added a deterministic PositionReview builder for scanner decay and regime
  shifts.
- Added conversion from PositionReview to a StrategistDecision candidate route.
- Added tests proving:
  - scanner decay on an open position can recommend hold without auto-close;
  - regime shift with weak edge recommends `tighten_exit`;
  - negative remaining edge plus positive net exit recommends close and can
    become a StrategistDecision close candidate;
  - negative edge without positive net exit recommends reduce, not scanner
    auto-close;
  - Guardian risk facts can recommend `close_now_if_risk_requires`;
  - missing open position produces explicit `no_action`.

What did not change:

- No runtime hot-path wiring.
- No deploy/rebuild/restart.
- No DB migration apply or DB write.
- No feature flag flip.
- No trading authority change.

Next AgentTodo item: MAG-043 consume Guardian rejection stats in next-cycle
decision.

Verification passed on Mac and Linux temp worktree:

- Mac Python PositionReview + Strategist V2 + spine client tests: 20 passed
- Mac py_compile passed
- Linux Python PositionReview + Strategist V2 + spine client tests: 20 passed
- Linux py_compile and diff whitespace checks passed
