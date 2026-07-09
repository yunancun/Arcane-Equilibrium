# AgentTodo MAG-052 Guardian P2 Modifications Report

Date: 2026-05-07
Role: PM / E1 local implementation checkpoint
Status: DONE

## Scope

Continued AgentTodo M5 Guardian V2 after MAG-051 and completed MAG-052:
add structured P2 risk modification output to Guardian verdict contracts and
Guardian runtime review.

## Result

Changed:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_contracts.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/multi_agent_framework.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/guardian_agent.py`
- `rust/openclaw_engine/src/agent_spine/contracts.rs`
- `rust/openclaw_engine/src/agent_spine/tests.rs`
- targeted Python tests for Guardian, framework, and spine client contracts

Guardian verdict contracts now carry `p2_modifications` entries with:

- bounded field: `size`, `leverage`, `stop`, or `cooldown`;
- action: `cap`, `reduce`, `tighten`, `extend`, or `set`;
- original/modified value, unit, reason code, reason, evidence refs, metadata.

Guardian runtime now:

- emits P2 modification records for moderate leverage cap;
- emits P2 size modification records for correlation soft limit and
  missing/incomplete same-direction matrix safe fallback;
- consumes per-strategy risk snapshots through provider/update API;
- soft strategy drawdown/loss-streak/loss-rate risk can modify size, leverage,
  stop-loss bps, and cooldown with reason codes;
- hard strategy drawdown/loss-streak rejects new opens, records
  `pause_new_entries`, and requests PositionReview evidence for active
  affected positions without direct-close authority.

## Boundary

No rebuild, restart, deploy, DB migration apply, DB write, feature-flag flip,
live auth mutation, trading mode change, or runtime strategy/risk config change
was performed.

Runtime source is not loaded until an operator-approved rebuild/restart.

## Verification

Mac:

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_guardian_agent_unit.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch8_guardian_integration.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_multi_agent_framework.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py -q` -> 150 passed
- `python3 -m py_compile` on touched Python app/test files
- `cargo fmt --manifest-path rust/openclaw_engine/Cargo.toml`
- `cargo test -p openclaw_engine agent_spine --manifest-path rust/Cargo.toml` -> 6 passed, pre-existing warnings only
- `git diff --check`

Linux `trade-core` temp worktree `/tmp/tradebot_mag052_guardian_p2_modifications`:

- same targeted Python pytest -> 150 passed
- same py_compile
- same Rust agent_spine cargo test -> 6 passed, pre-existing warnings only
- `git diff --check`

## Next AgentTodo Item

Next: MAG-053 consume Scout event alerts and scanner risk evidence in Guardian.
