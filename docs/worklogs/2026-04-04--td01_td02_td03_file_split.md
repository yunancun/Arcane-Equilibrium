# 2026-04-04 Session 3 — TD-01/TD-02/TD-03 Python File Splitting

## Summary

Completed all 3 technical debt items (Python file splitting) required before Phase 1.

---

## TD-01: pipeline_bridge.py (2587 → 4 files)

**Approach:** Python mixin pattern — 3 mixin classes + thin facade.

| File | Lines | Content |
|------|-------|---------|
| `pipeline_bridge.py` | 55 | Facade: `PipelineBridge(_BridgeCoreMixin, _BridgeAgentsMixin, _BridgeStatsMixin)` |
| `bridge_core.py` | 831 | `__init__`, 17 `set_*`, lifecycle, `on_tick`, `_tick_*`, intent pipeline, `_submit_approved_intent` |
| `bridge_agents.py` | 919 | `_gate_intent`, `_post_execution_hooks`, `_check_stops`, `_invoke_scout_scan`, `_try_l2_cron_trigger`, `_check_edge_filter` |
| `bridge_stats.py` | 825 | `_on_position_open`, `_try_learning_promotion`, `_emit_round_trip`, `on_tick_result`, market data, `get_stats` |

- 52/52 methods verified via AST comparison
- All existing `from .pipeline_bridge import PipelineBridge` imports remain valid

## TD-02: phase2_strategy_routes.py (1838 → 5 files)

**Approach:** Extract wiring + split routes by function + facade re-exports.

| File | Lines | Content |
|------|-------|---------|
| `phase2_strategy_routes.py` | 81 | Facade: `from .strategy_wiring import *` + route module imports + explicit re-exports |
| `strategy_wiring.py` | 1180 | All singletons, DI wiring, agent creation, router creation, helpers |
| `strategy_read_routes.py` | 396 | 13 GET routes (klines, indicators, signals, strategies, pipeline, scanner, kelly) |
| `strategy_write_routes.py` | 223 | 6 POST routes (activate, pause, stop, create, delete, toggle_dynamic_risk) |
| `strategy_ai_routes.py` | 141 | 7 GET routes (demo status/balance/positions/orders/fills, telegram, AI consultation) |

- 26/26 routes verified via AST comparison
- All existing imports remain valid via facade re-exports

## TD-03: paper_trading_routes.py (1144 → 857 lines, -25%)

**Approach:** Extract governance/TTL/H0 wiring into `paper_trading_wiring.py`.

| File | Lines | Content |
|------|-------|---------|
| `paper_trading_routes.py` | 857 | Routes + facade re-exports from wiring |
| `paper_trading_wiring.py` | 488 | Singletons: ENGINE, GOV_HUB, RISK_MANAGER, H0_GATE, TTL_ENFORCER, etc. |

- 25/25 routes verified
- `DISPATCHER`/`SHADOW_CONSUMER` kept as mutable globals in routes (required by `global` rebinding)

---

## E2 Review Findings (all fixed)

| Finding | Severity | Fix |
|---------|----------|-----|
| Dead imports in bridge_core.py (REGIME_TIME_MULTIPLIERS, DataQualityLevel) | LOW | Removed |
| PAPER_ENGINE missing from strategy_wiring.__all__ | BLOCKING | Added |
| _STRATEGY_NAME_PATTERN missing from strategy_wiring.__all__ | BLOCKING | Added |
| Dead fastapi imports in strategy_wiring.py (Body, Depends, etc.) | LOW | Trimmed to APIRouter only |
| Dead `base`, `get_rust_reader` imports in strategy_wiring.py | LOW | Removed |
| Test mock.patch targets wrong module after split | BLOCKING | Updated _MOD_READ/_MOD_WRITE/_MOD_AI |
| Test logger patches wrong module (app.pipeline_bridge → app.bridge_core/bridge_stats) | BLOCKING | Updated to correct modules |

## Test Results

```
Python: 3839 passed, 5 flaky (pre-existing test isolation, pass individually)
Rust:   690 passed, 0 failed
Total:  4529 tests
Split-caused failures: 0 (all fixed)
```

## File Size Summary (all under 1200 hard limit)

```
bridge_core.py:           831
bridge_agents.py:         919
bridge_stats.py:          825
pipeline_bridge.py:        55
strategy_wiring.py:      1180
strategy_read_routes.py:  396
strategy_write_routes.py: 223
strategy_ai_routes.py:    141
phase2_strategy_routes.py: 81
paper_trading_wiring.py:  488
paper_trading_routes.py:  857
```
