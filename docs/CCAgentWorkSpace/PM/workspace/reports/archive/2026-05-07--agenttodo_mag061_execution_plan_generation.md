# AgentTodo MAG-061 ExecutionPlan Generation Report

Date: 2026-05-07
Role: PM / E1 local implementation checkpoint
Status: DONE

## Scope

Continued AgentTodo M6 Executor Planner by completing MAG-061: implement
deterministic ExecutionPlan generation from an approved or modified
StrategistDecision + GuardianVerdict lineage.

## Result

Added:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_plan_v2.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_plan_v2.py`

Generation gates:

- rejected GuardianVerdict cannot produce an ExecutionPlan.
- GuardianVerdict decision id, engine mode, symbol, and strategy must match the
  StrategistDecision.
- `hold` and `no_action` decisions are fail-closed.
- `open` decisions require Strategist-provided `long` / `short` direction.
- `reduce` / `close` decisions require Strategist-provided `close_long` /
  `close_short`; Executor does not infer close direction from `long` / `short`.
- generated plans copy symbol, direction, strategy, and engine mode from
  StrategistDecision and set `symbol_source` / `direction_source` to
  `strategist_decision`.
- Guardian P2 `size` modifications cap quantity; P2 `stop`, `cooldown`, and
  `leverage` become bounded plan policy metadata without changing trade scope.
- price-bearing open decisions become post-only maker plans; market entry plans
  carry bounded slippage and taker allowance; close/reduce plans become
  reduce-only market exit plans with high urgency and `TRADE_EXIT` lease scope.

## Boundary

No runtime submit wiring, Decision Lease acquisition, rebuild, restart, deploy,
DB migration apply, DB write, feature-flag flip, live auth mutation, trading
mode change, or runtime strategy/risk config change was performed.

Runtime source is not loaded until an operator-approved rebuild/restart.

## Verification

Mac:

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_plan_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_plan_v2.py`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_plan_v2.py -q` -> 9 passed
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_plan_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py -q` -> 22 passed
- `git diff --check`

Linux `trade-core` temp worktree `/tmp/tradebot_mag061_execution_plan_generation`:

- same Python py_compile
- same targeted pytest -> 22 passed
- `git diff --check`

## Dispatch Note

Repo workflow normally expects PM -> PA/E1/E2/E4, but this Codex runtime allows
sub-agents only when the operator explicitly asks for delegation. This MAG-061
checkpoint was therefore handled locally with targeted implementation and
regression checks.

## Next AgentTodo Item

Next: MAG-062 bind ExecutionPlan to Decision Lease before any real submit path.
