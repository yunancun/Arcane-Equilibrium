# AgentTodo MAG-053 Event / Scanner Risk Guardian Report

Date: 2026-05-07
Role: PM / E1 local implementation checkpoint
Status: DONE

## Scope

Continued AgentTodo M5 Guardian V2 after MAG-052 and completed MAG-053:
consume Scout event alerts and scanner risk evidence inside Guardian review.

## Result

Changed:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/guardian_agent.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_guardian_agent_unit.py`

Guardian now:

- initializes Scout event alert risk from Scout severity when no L1
  classification is available;
- stores RISK_PATTERN payloads as active risk evidence for later review;
- reads scanner risk evidence from `TradeIntent.metadata` or `params`;
- matches event/scanner evidence by symbol and strategy;
- lets high/soft event or scanner risk emit P2 size/cooldown modifications
  with reason codes;
- lets critical/hard event or scanner risk reject/pause new opens and request
  PositionReview evidence for active affected positions;
- keeps all event/scanner evidence advisory to Guardian risk review only:
  no symbol/direction mutation, no order creation, and no direct close output.

## Boundary

No rebuild, restart, deploy, DB migration apply, DB write, feature-flag flip,
live auth mutation, trading mode change, or runtime strategy/risk config change
was performed.

Runtime source is not loaded until an operator-approved rebuild/restart.

## Verification

Mac:

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_guardian_agent_unit.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch8_guardian_integration.py -q` -> 74 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/guardian_agent.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_guardian_agent_unit.py`
- `git diff --check`

Linux `trade-core` temp worktree `/tmp/tradebot_mag053_event_scanner_risk_guardian`:

- same targeted pytest -> 74 passed
- same py_compile
- `git diff --check`

## Next AgentTodo Item

Next: MAG-054 regression: Guardian verdict is mandatory before ExecutionPlan.
