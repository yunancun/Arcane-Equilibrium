# AgentTodo MAG-062 ExecutionPlan Lease Binding Report

Date: 2026-05-07
Role: PM / E1 local implementation checkpoint
Status: DONE

## Scope

Continued AgentTodo M6 Executor Planner by completing MAG-062: bind Decision
Lease IDs to ExecutionPlan objects and enforce fail-closed behavior before any
real submit boundary.

## Result

Changed:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_plan_v2.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_plan_v2.py`

Lease gates:

- `acquire_execution_plan_lease()` calls `GovernanceHub.acquire_lease()` using
  `order_plan_id` as the lease intent id, plus the plan's `lease_scope` and
  `lease_ttl_ms`.
- lease acquisition returns a validated copy of the plan with `lease_id` bound
  and binding metadata preserved.
- `prepare_execution_plan_for_submit(real_submit=True)` fails closed if the
  plan has no lease and no GovernanceHub, if acquisition fails, or if lease
  request fields are missing.
- `require_execution_plan_lease_for_submit(real_submit=True)` refuses an
  unleased plan.
- shadow / pre-submit planning can remain unleased, so durable plan persistence
  is still separated from real order submission.

## Boundary

No runtime submit wiring, IPC protocol change, Rust `SubmitOrder` shape change,
rebuild, restart, deploy, DB migration apply, DB write, feature-flag flip, live
auth mutation, trading mode change, or runtime strategy/risk config change was
performed.

Runtime source is not loaded until an operator-approved rebuild/restart.

## Verification

Mac:

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_plan_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_plan_v2.py`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_plan_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py -q` -> 28 passed
- `git diff --check`

Linux `trade-core` temp worktree `/tmp/tradebot_mag062_execution_plan_lease_binding`:

- same Python py_compile
- same targeted pytest -> 28 passed
- `git diff --check`

## Dispatch Note

Sub-agent dispatch was not used because this Codex runtime only allows
sub-agents when the operator explicitly requests delegation.

## Next AgentTodo Item

Next: MAG-063 persist ExecutionReport quality metrics for Analyst consumption.
