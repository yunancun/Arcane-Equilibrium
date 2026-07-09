# W-AUDIT-3 F-01 Provider Fail-Closed Source Checkpoint

**Date**: 2026-05-09  
**Owner**: PM local implementation  
**Scope**: `P1-AUDIT-RUNTIME-3` / `W-AUDIT-3` / SM-05 F-01  
**Status**: Source/test closed

## Summary

F-01 removed the hidden `lambda: True` fallback from
`ExecutorAgent.__init__`. Production construction remains explicit through
`strategy_wiring.py`:

```python
shadow_mode_provider=_EXECUTOR_CONFIG_CACHE.shadow_mode_provider()
```

When a provider is missing in standalone/test construction, or when the
provider raises, `ExecutorAgent._read_shadow_mode()` now performs the
fail-closed decision explicitly and returns `shadow_mode=True`. This suppresses
IPC submit authority before the Rust submit path is reached.

## Files Changed

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_lease_bridge.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_agent_unit.py`
- `TODO.md`
- `CLAUDE.md`
- `docs/governance_dev/SPECIFICATION_REGISTER.md`
- `docs/governance_dev/amendments/2026-05-09--SM-05_executor_shadow_mode_polling_design.md`
- `docs/governance_dev/amendments/2026-05-09--operator_decision_audit_closure.md`

## Verification

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py`
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_agent_unit.py`
  - 30 passed
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_config_cache.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_decision_parity.py`
  - 17 passed, 7 skipped
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agents_routes.py -k "executor or shadow"`
  - 7 passed, 18 deselected

## Boundary

Source/test/documentation only. No rebuild, restart, deploy, DB migration, live
auth mutation, true-live API use, scanner authority change, strategy/risk config
mutation, MAG-083/084 unlock, or Executor hard authority grant was performed.
