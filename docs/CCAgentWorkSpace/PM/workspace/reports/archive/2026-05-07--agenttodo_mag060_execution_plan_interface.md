# AgentTodo MAG-060 ExecutionPlan Interface Report

Date: 2026-05-07
Role: PM / PA local contract checkpoint
Status: DONE

## Scope

Started AgentTodo M6 Executor Planner and completed MAG-060: define the
ExecutionPlan interface and allowed order styles so Executor can optimize
execution quality without acquiring symbol or direction authority.

## Result

Added:

- `docs/architecture/multi_agent_rework_2026-05-05/2026-05-07--mag060_execution_plan_interface.md`

Changed:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_contracts.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_spine_client.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py`
- `rust/openclaw_engine/src/agent_spine/contracts.rs`
- `rust/openclaw_engine/src/agent_spine/events.rs`
- `rust/openclaw_engine/src/agent_spine/tests.rs`

Contract gates:

- ExecutionPlan now carries `verdict_version`, `symbol_source`,
  `direction_source`, `reduce_only`, `order_style`, `urgency`,
  `max_slippage_bps`, `maker_preference`, stop handoff policy fields, and
  lease request fields.
- Allowed order styles are `market`, `limit`, `post_only`, `twap`, and `split`.
- Python contract validation rejects invalid order-style combinations.
- Python spine client rejects ExecutionPlan publication unless the plan matches
  a known/fetched StrategistDecision and an approved/modified GuardianVerdict.
- Rust contracts mirror the new execution-style enums and authority-source
  fields; idempotency details now include order style and verdict version.

## Boundary

No rebuild, restart, deploy, DB migration apply, DB write, feature-flag flip,
live auth mutation, trading mode change, runtime order submit path change, or
runtime strategy/risk config change was performed.

Runtime source is not loaded until an operator-approved rebuild/restart.

## Verification

Mac:

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py -q` -> 13 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_contracts.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_spine_client.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py`
- `cargo fmt --manifest-path rust/openclaw_engine/Cargo.toml`
- `cargo test -p openclaw_engine agent_spine --manifest-path rust/Cargo.toml` -> 6 passed, pre-existing warnings only
- `git diff --check`

Linux `trade-core` temp worktree `/tmp/tradebot_mag060_execution_plan_interface`:

- same Python spine-client pytest -> 13 passed
- same py_compile
- same Rust agent_spine cargo test -> 6 passed, pre-existing warnings only
- `git diff --check`

## Next AgentTodo Item

Next: MAG-061 implement ExecutionPlan generation from approved/modified
StrategistDecision + GuardianVerdict lineage.
