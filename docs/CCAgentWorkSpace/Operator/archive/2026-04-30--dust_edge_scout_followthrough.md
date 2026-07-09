# Dust / Edge / Scout Follow-through

Date: 2026-04-30
Owner: PM

## Result

- Dust residual runtime proof is complete: after the 2026-04-30 21:10 CEST runtime load, 8 Demo/LiveDemo `qty=0` close orders joined to nonzero fills.
- Key proof rows: Demo `APEUSDT` `orphan_frozen` fill qty 0.1 and LiveDemo `XAGUSDT` `orphan_frozen` fill qty 0.001, both from `risk_close:ipc_close_symbol`, both with no later position snapshot.
- Post-deploy edge cutoff observation is started but still under-sampled: `[33]` n=15 maker_like 40.0% / fee_drop 39.0%; `[38]` lifecycle n=1+1 insufficient; `[40]` rows=0.
- Scout heartbeat production caller wiring is complete: ScoutWorker completed scan paths now call `ScoutAgent.record_scan()`.

## Verification

- `test_strategy_wiring_scanner.py`: 2 passed.
- `test_agent_heartbeat_contract.py`: 36 passed.
- Targeted `py_compile`: passed.

## Boundary

- No strategy/risk config changes.
- No live authorization changes.
- API-only reload applied the Python Scout heartbeat wiring; Rust engine was not rebuilt or restarted.
- Runtime after reload: API uvicorn PID `1591455`, engine PID `1529433`, watchdog `engine_alive=true`.
