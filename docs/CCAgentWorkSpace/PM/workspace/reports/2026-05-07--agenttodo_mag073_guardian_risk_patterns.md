# AgentTodo MAG-073 Guardian Risk Patterns

Date: 2026-05-07
Owner: PM-local execution
Status: DONE

## Scope

Ensure Guardian consumes Analyst risk patterns as evidence that can tighten P2
without changing P0/P1 authority boundaries.

## Implementation

- Updated `guardian_agent.py` `RISK_PATTERN` handling to preserve:
  - `insight_id`
  - `analyst_tier`
  - `insight_type`
  - `insight_level`
  - `evidence_refs`
  - symbol/strategy/risk score/reason codes
- Risk-pattern evidence now maps to `risk_pattern_soft_risk` or
  `risk_pattern_hard_risk` reason codes when the source is Analyst
  risk-pattern evidence.
- Added a Guardian regression proving an L2 Analyst risk pattern P2-tightens
  size/cooldown while never adding symbol/direction or direct close/order
  authority.

## Verification

- Mac:
  - `python3 -m py_compile ... guardian_agent.py test_guardian_agent_unit.py`
  - `python3 -m pytest ... test_guardian_agent_unit.py -q`
  - `git diff --check`
- Linux `trade-core` temp worktree:
  - same py_compile
  - same pytest set
  - same diff check

Focused result: 45 Python tests pass.

## Boundary

- No runtime Guardian wiring.
- No runtime Analyst emission wiring.
- No Strategist behavior change.
- No cloud call.
- No runtime submit path.
- No Rust contract change.
- No rebuild, restart, deploy, DB write, live auth, runtime flag, or trading
  authority change.

## Next

M7 continues with MAG-074 end-to-end losing-pattern regression.
