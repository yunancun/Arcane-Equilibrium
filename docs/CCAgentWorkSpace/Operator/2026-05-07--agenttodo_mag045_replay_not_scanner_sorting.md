# AgentTodo MAG-045 Replay Not Scanner Sorting Operator Report

Date: 2026-05-07
Status: DONE

Completed MAG-045 and closed M4 Strategist V2.

What changed:

- Candidate scores now include `scanner_rank`.
- Added a replay-style regression where scanner rank 1 is not selected.
- The selected route is chosen because net edge plus Guardian/Analyst evidence
  beats raw scanner rank.
- The regression requires explicit thesis, invalidation, rank comparison,
  Guardian feedback, learning feedback, and evidence refs.

What did not change:

- No runtime hot-path wiring.
- No deploy/rebuild/restart.
- No DB migration apply or DB write.
- No feature flag flip.
- No trading authority change.

Next AgentTodo item: M5 / MAG-050 design dynamic correlation and per-strategy
drawdown metrics.

Verification passed on Mac and Linux temp worktree:

- Mac Python replay-style Strategist V2 + PositionReview + spine client tests:
  29 passed
- Mac py_compile and diff whitespace checks passed
- Linux Python replay-style Strategist V2 + PositionReview + spine client
  tests: 29 passed
- Linux py_compile and diff whitespace checks passed
