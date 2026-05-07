# AgentTodo MAG-045 Replay Not Scanner Sorting Report

Date: 2026-05-07
Role: PM / E4 local regression checkpoint
Status: DONE

## Scope

Closed AgentTodo M4 by adding a replay-style regression proving Strategist V2
decisions are not equivalent to raw scanner score sorting.

## Result

Updated:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_decision_v2.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_v2_replay_not_scanner_sorting.py`

The test fixture builds a deterministic replay match where:

- scanner rank 1 is `grid_trading`;
- scanner rank 2 is `ma_crossover`;
- Guardian feedback shows high recent reject rate for `grid_trading`;
- AnalystInsight carries a losing grid pattern;
- Strategist V2 selects `ma_crossover`, not the raw rank-1 route.

Candidate scores now include `scanner_rank`, plus Guardian and learning
feedback. The regression asserts selected candidate rank, top-rank reject
reason, explicit thesis/invalidation, and preserved evidence refs.

## Boundary

No runtime deploy, rebuild, restart, DB migration apply, DB write, feature-flag
flip, live auth mutation, trading mode change, or risk/strategy config change
was performed.

This is a typed helper regression. It is not wired into `StrategistAgent`
runtime hot path yet.

## Verification

Mac:

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_v2_replay_not_scanner_sorting.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_position_review_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py -q`
  - 29 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_v2_replay_not_scanner_sorting.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py`
- `git diff --check`

Linux `trade-core` temp worktree `/tmp/tradebot_mag045_replay_sorting`:

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_v2_replay_not_scanner_sorting.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_position_review_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py -q`
  - 29 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_v2_replay_not_scanner_sorting.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py`
- `git diff --check --cached`

## Next AgentTodo Item

Next: M5 / MAG-050 design dynamic correlation and per-strategy drawdown metrics.
