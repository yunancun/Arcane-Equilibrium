# AgentTodo MAG-050 Guardian V2 Risk Metrics Model Report

Date: 2026-05-07
Role: PM / QC local design checkpoint
Status: DONE

## Scope

Started AgentTodo M5 Guardian V2 and completed MAG-050: design dynamic
correlation and per-strategy drawdown metrics.

## Result

Added:

- `docs/architecture/multi_agent_rework_2026-05-05/2026-05-07--mag050_guardian_v2_risk_metrics_model.md`

The contract defines:

- `CorrelationSnapshot` inputs and quality/fallback semantics;
- `CorrelationReviewInput` and same-direction pair review rules;
- safe fallback behavior when the matrix is missing or stale;
- `StrategyRiskSnapshot` inputs for per-strategy drawdown/loss-streak review;
- drawdown states and Guardian effects;
- GuardianVerdict mapping for reject/modify/pause/review behavior;
- required MAG-051 and MAG-052 regression targets.

## Boundary

No runtime deploy, rebuild, restart, DB migration apply, DB write, feature-flag
flip, live auth mutation, trading mode change, or risk/strategy config change
was performed.

This is a docs/contract checkpoint only.

## Verification

Mac:

- `git diff --check`

Linux `trade-core` temp worktree `/tmp/tradebot_mag050_guardian_contract`:

- `git diff --check --cached`

## Next AgentTodo Item

Next: MAG-051 replace hardcoded BTC/ETH-only correlation with dynamic matrix or
safe fallback.
