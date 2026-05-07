# AgentTodo MAG-064 Executor Scope Regression

Date: 2026-05-07
Owner: PM-local execution
Status: DONE

## Scope

Close M6 Executor Planner by adding focused regressions for:

- Executor plan generation cannot choose or alter symbol/direction.
- ExecutionPlan scope sources must remain `strategist_decision`.
- Agent Spine persistence refuses an ExecutionPlan whose symbol/direction
  diverges from the prior approved StrategistDecision.

## Implementation

- Added `test_executor_plan_scope_is_copied_only_from_approved_decision()` in
  `test_executor_plan_v2.py`.
- Added `test_execution_plan_contract_forbids_non_strategist_scope_sources()`
  in `test_agent_spine_client.py`.
- Expanded the Agent Spine publish regression to cover both symbol and
  direction divergence from the approved StrategistDecision.
- Updated AgentTodo/TODO/PM memory to mark MAG-064 and M6 closed.

## Verification

- Mac:
  - `python3 -m py_compile ... executor_plan_v2.py test_executor_plan_v2.py agent_spine_client.py test_agent_spine_client.py`
  - `python3 -m pytest ... test_executor_plan_v2.py ... test_agent_spine_client.py -q`
  - `git diff --check`
- Linux `trade-core` temp worktree:
  - same py_compile
  - same pytest set
  - same diff check

Expected focused result: 32 Python tests pass.

## Boundary

- No runtime submit wiring.
- No IPC protocol or Rust contract changes.
- No rebuild, restart, deploy, DB write, live auth, runtime flag, or trading
  authority change.

## Next

M7 starts at MAG-070 AnalystInsight L1/L2/L3 schema.
