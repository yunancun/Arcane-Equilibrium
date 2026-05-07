# AgentTodo MAG-051 Dynamic Correlation Guardian Report

Date: 2026-05-07
Role: PM / E1 local implementation checkpoint
Status: DONE

## Scope

Continued AgentTodo M5 Guardian V2 after MAG-050 and completed MAG-051:
replace the legacy BTC/ETH-only correlation authority with dynamic correlation
snapshot review or explicit safe fallback behavior.

## Result

Changed:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/guardian_agent.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_guardian_agent_unit.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch8_guardian_integration.py`

Guardian now:

- accepts a dynamic correlation snapshot through constructor provider or
  `update_correlation_snapshot()`;
- removes the static BTC/ETH-only hardcoded pair authority;
- reviews same-direction active positions against any symbol pair in the
  dynamic matrix;
- rejects hard same-direction breaches when sample count is sufficient;
- returns `MODIFIED` with a conservative size cap for soft correlation or
  missing/stale/incomplete same-direction matrix evidence;
- records `correlation_review` metadata with pair, `r`, sample count,
  threshold, source/quality, and reason codes;
- records `correlation_data_insufficient` for missing matrix evidence without
  treating missing data as positive evidence;
- records opposite-side positions as hedge/correlation evidence without using
  the same hard reject path.

## Boundary

No rebuild, restart, deploy, DB migration apply, DB write, feature-flag flip,
live auth mutation, trading mode change, or risk/strategy config change was
performed.

Runtime source is not loaded until an operator-approved rebuild/restart.

## Verification

Mac:

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_guardian_agent_unit.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch8_guardian_integration.py -q` -> 69 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/guardian_agent.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_guardian_agent_unit.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch8_guardian_integration.py`
- `git diff --check`

Linux `trade-core` temp worktree `/tmp/tradebot_mag051_dynamic_correlation`:

- same targeted pytest -> 69 passed
- same py_compile
- `git diff --check`

## Next AgentTodo Item

Next: MAG-052 add P2 risk modification output to GuardianVerdict.
