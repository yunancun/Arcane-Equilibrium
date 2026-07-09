# AgentTodo MAG-034 Idempotency Audit Report

Date: 2026-05-07
Role: PM / E2 local audit checkpoint
Status: DONE

## Scope

Continued AgentTodo M3 after MAG-033 and audited double-execution prevention
for the default-disabled Agent Spine shadow surface.

## Result

MAG-034 is approved for MAG-035 shadow integration.

The audit confirms that execution candidates carry:

- `decision_id`
- `order_plan_id`
- `idempotency_key`
- `engine_mode`

The DB schema, Rust contracts/events, Rust writer surface, Python contracts, and
Python client all preserve those ids. V064 has primary/unique constraints for
idempotency key, plan/mode, and decision/plan/mode. Python `ExecutionPlan` and
`ExecutionReport` reject missing lineage ids.

Audit note:
`docs/architecture/multi_agent_rework_2026-05-05/2026-05-07--mag034_idempotency_double_execution_audit.md`

## Boundary

No runtime deploy, rebuild, restart, DB migration apply, DB write, feature-flag
flip, live auth mutation, trading mode change, or risk/strategy config change
was performed.

This is source-level and schema-level audit closure only. Runtime primary/canary
enforcement remains later work.

## Verification

Mac:

- `cargo fmt -p openclaw_engine --check` from `srv/rust`
- `cargo test -p openclaw_engine agent_spine --features replay_isolated` from `srv/rust`
  - 5 passed
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py tests/migrations/test_v064_agent_spine_decision_store.py -q`
  - 12 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_contracts.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_spine_client.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py`
- `git diff --check`

Linux `trade-core` temp worktree `/tmp/tradebot_mag034_idempotency_audit`:

- `PATH=$HOME/.cargo/bin:$PATH cargo fmt -p openclaw_engine --check` from `srv/rust`
- `PATH=$HOME/.cargo/bin:$PATH cargo test -p openclaw_engine agent_spine --features replay_isolated` from `srv/rust`
  - 5 passed
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py tests/migrations/test_v064_agent_spine_decision_store.py -q`
  - 12 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_contracts.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_spine_client.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py`
- `git diff --check --cached`

## Next AgentTodo Item

Next: MAG-035 shadow integration test: legacy Rust path vs spine decisions.
