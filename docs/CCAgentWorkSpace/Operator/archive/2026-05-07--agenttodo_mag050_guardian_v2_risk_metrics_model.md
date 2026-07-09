# AgentTodo MAG-050 Guardian V2 Risk Metrics Model Operator Report

Date: 2026-05-07
Status: DONE

Completed MAG-050.

What changed:

- Added the Guardian V2 risk metrics contract.
- Defined dynamic correlation snapshot inputs and fallback behavior.
- Defined per-strategy drawdown and loss-streak metrics.
- Defined how Guardian should map those signals into reject / modify / pause /
  PositionReview outcomes.
- Defined required regressions for MAG-051 and MAG-052.

What did not change:

- No runtime behavior.
- No deploy/rebuild/restart.
- No DB migration apply or DB write.
- No feature flag flip.
- No trading authority change.

Next AgentTodo item: MAG-051 replace hardcoded BTC/ETH-only correlation with
dynamic matrix or safe fallback.

Verification passed on Mac and Linux temp worktree:

- Mac `git diff --check` passed
- Linux `git diff --check --cached` passed
