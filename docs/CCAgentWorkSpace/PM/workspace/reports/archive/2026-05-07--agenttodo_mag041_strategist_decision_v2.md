# AgentTodo MAG-041 StrategistDecision V2 Report

Date: 2026-05-07
Role: PM / E1a local implementation checkpoint
Status: DONE

## Scope

Continued AgentTodo M4 after MAG-040 and implemented a typed Strategist V2
decision builder for:

- `open`
- `hold`
- `reduce`
- `close`
- `no_action`

## Result

Added:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_decision_v2.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py`

Updated:

- Python `StrategistDecision` contract with MAG-040 fields:
  - `decision_action`
  - `selected_strategy`
  - `selected_candidate_id`
  - `candidate_scores`
  - `expected_net_edge_bps`
  - `portfolio_impact`
  - `thesis`
  - `invalidation`
  - separated `fact_refs` / `inference_refs` / `hypothesis_refs`
- Rust `agent_spine::contracts::StrategistDecision` mirror fields.

The deterministic builder selects canonical strategy keys, normalizes supported
aliases, records candidate scores/reject reasons, blocks negative-net-LCB new
opens, allows tactical reduce/close only with position-review lineage, and
returns explicit `no_action` when evidence is missing or all candidates reject.

## Boundary

No runtime deploy, rebuild, restart, DB migration apply, DB write, feature-flag
flip, live auth mutation, trading mode change, or risk/strategy config change
was performed.

This is a typed helper and contract implementation. It is not wired into
`StrategistAgent` runtime hot path yet.

## Verification

Mac:

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py -q`
  - 14 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_contracts.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py`
- `cargo fmt -p openclaw_engine --check` from `srv/rust`
- `cargo test -p openclaw_engine agent_spine --features replay_isolated` from `srv/rust`
  - 6 passed
- `git diff --check`

Linux `trade-core` temp worktree `/tmp/tradebot_mag041_strategist_decision`:

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py -q`
  - 14 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_contracts.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py`
- `PATH=$HOME/.cargo/bin:$PATH cargo fmt -p openclaw_engine --check` from `srv/rust`
- `PATH=$HOME/.cargo/bin:$PATH cargo test -p openclaw_engine agent_spine --features replay_isolated` from `srv/rust`
  - 6 passed
- `git diff --check --cached`

## Next AgentTodo Item

Next: MAG-042 PositionReview for scanner decay and regime shifts.
