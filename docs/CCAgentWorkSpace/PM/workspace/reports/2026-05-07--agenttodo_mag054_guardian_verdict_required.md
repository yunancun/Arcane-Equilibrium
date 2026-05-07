# AgentTodo MAG-054 Guardian Verdict Required Report

Date: 2026-05-07
Role: PM / E4 local regression checkpoint
Status: DONE

## Scope

Closed AgentTodo M5 Guardian V2 by completing MAG-054: regression that
ExecutionPlan cannot be created without an approved/modified Guardian verdict.

## Result

Changed:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_contracts.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_spine_client.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py`
- `rust/openclaw_engine/src/agent_spine/events.rs`
- `rust/openclaw_engine/src/agent_spine/tests.rs`

Regression gates:

- `ExecutionPlan.verdict_id` must be non-empty.
- `AgentSpineClient.publish_execution_plan()` fail-soft rejects a plan when no
  allowing GuardianVerdict is known or present.
- a rejected GuardianVerdict cannot authorize an ExecutionPlan.
- a P2-modified GuardianVerdict is persisted as state `modified`, distinct from
  plain `approved` and from `rejected`.
- Rust spine envelopes also classify P2-modified Guardian verdicts as
  `modified`.

## Boundary

No rebuild, restart, deploy, DB migration apply, DB write, feature-flag flip,
live auth mutation, trading mode change, or runtime strategy/risk config change
was performed.

Runtime source is not loaded until an operator-approved rebuild/restart.

## Verification

Mac:

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py -q` -> 11 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_spine_client.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_contracts.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py`
- `cargo fmt --manifest-path rust/openclaw_engine/Cargo.toml`
- `cargo test -p openclaw_engine agent_spine --manifest-path rust/Cargo.toml` -> 6 passed, pre-existing warnings only
- `git diff --check`

Linux `trade-core` temp worktree `/tmp/tradebot_mag054_guardian_verdict_required`:

- same Python spine-client pytest -> 11 passed
- same py_compile
- same Rust agent_spine cargo test -> 6 passed, pre-existing warnings only
- `git diff --check`

## Next AgentTodo Item

M5 Guardian V2 is closed. Next milestone: M6 / MAG-060 define ExecutionPlan
interface and allowed order styles.
