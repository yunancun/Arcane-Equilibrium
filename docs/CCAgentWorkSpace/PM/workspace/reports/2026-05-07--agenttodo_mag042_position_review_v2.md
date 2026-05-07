# AgentTodo MAG-042 PositionReview V2 Report

Date: 2026-05-07
Role: PM / E1a local implementation checkpoint
Status: DONE

## Scope

Continued AgentTodo M4 after MAG-041 and implemented a typed Strategist V2
PositionReview helper for scanner decay and regime-shift review.

## Result

Added:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/position_review_v2.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_position_review_v2.py`

Updated:

- Python `agent_contracts.py` with `PositionReview`, review recommendation,
  trigger, and urgency contract literals.

The deterministic builder turns open-position scanner decay, regime shift,
negative remaining edge, positive net-exit opportunity, adverse PnL drift,
cost-edge deterioration, time-stop pressure, and Guardian risk facts into
explicit recommendations:

- `hold`
- `reduce`
- `tighten_exit`
- `stop_adding`
- `close_when_net_positive`
- `close_now_if_risk_requires`
- `no_action`

Scanner decay remains advisory: the review always emits
`allow_auto_close=false`, ignores any malformed decay `auto_close_allowed=true`
flag, and requires Guardian lineage for reduce/close recommendations.

## Boundary

No runtime deploy, rebuild, restart, DB migration apply, DB write, feature-flag
flip, live auth mutation, trading mode change, or risk/strategy config change
was performed.

This is a typed helper and contract implementation. It is not wired into
`StrategistAgent`, Guardian, Executor, or the Rust runtime hot path yet.

## Verification

Mac:

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_position_review_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py -q`
  - 20 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_contracts.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/position_review_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_position_review_v2.py`

Linux `trade-core` temp worktree `/tmp/tradebot_mag042_position_review`:

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_position_review_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py -q`
  - 20 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_contracts.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/position_review_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_position_review_v2.py`
- `git diff --check --cached`

## Next AgentTodo Item

Next: MAG-043 consume Guardian rejection stats in next-cycle decision.
