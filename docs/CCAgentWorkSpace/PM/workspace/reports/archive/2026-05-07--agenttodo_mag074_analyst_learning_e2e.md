# AgentTodo MAG-074 Analyst Learning E2E

Date: 2026-05-07
Owner: PM-local execution
Status: DONE

## Scope

Close M7 with an end-to-end regression for:

- losing-pattern AnalystInsight persistence,
- evidence edge persistence,
- Strategist next-cycle preference change,
- persisted StrategistDecision reason/evidence.

## Implementation

- Added `test_losing_pattern_to_strategist_weight_change_persists_reason()` in
  `test_agent_spine_client.py`.
- The regression persists an L2 losing-pattern AnalystInsight with round-trip
  and strategy-metric evidence refs.
- It then feeds the same typed insight into StrategistDecision V2, proves the
  selected strategy moves away from the losing grid route, publishes the
  StrategistDecision, and asserts the persisted payload carries the typed
  learning reason and evidence refs.

## Verification

- Mac:
  - `python3 -m py_compile ... agent_spine_client.py strategist_decision_v2.py test_agent_spine_client.py`
  - `python3 -m pytest ... test_agent_spine_client.py test_strategist_decision_v2.py test_strategist_v2_replay_not_scanner_sorting.py -q`
  - `git diff --check`
- Linux `trade-core` temp worktree:
  - same py_compile
  - same pytest set
  - same diff check

Focused result: 35 Python tests pass.

## Boundary

- No runtime Strategist, Analyst, or Guardian wiring.
- No cloud call.
- No runtime submit path.
- No Rust contract change.
- No rebuild, restart, deploy, DB write, live auth, runtime flag, or trading
  authority change.

## Next

M8 starts with MAG-080 cutover policy.
