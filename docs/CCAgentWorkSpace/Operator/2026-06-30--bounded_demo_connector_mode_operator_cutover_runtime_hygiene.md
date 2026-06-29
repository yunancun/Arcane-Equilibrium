# Bounded Demo Connector Mode Cutover + Runtime Hygiene

Operator clarification accepted: `FWkGZX...g53T` is the correct Bybit Demo Read-Write key. The prior `BHw4...` mismatch was a stale expected hint, not a bad Demo key and not a live/mainnet issue.

`BYBIT_MODE=read_only` was a local runtime gate. It has now been cut over through the approved settings API to:

- `BYBIT_MODE=demo`
- `BYBIT_CONNECTOR_WRITE_ENABLED=true`

Mainnet remains disabled: `OPENCLAW_ALLOW_MAINNET=0`.

Runtime evidence:

- API service is back under `openclaw-trading-api.service`, MainPID `1038429`, `NRestarts=0`.
- `/openapi.json` returns `200`.
- Settings GET reports `configured_ready=True`, `runtime_ready=True`, `restart_required=False`.
- Readiness artifact is `BOUNDED_DEMO_RUNTIME_READY_FOR_FINAL_WINDOW_GATES`.
- Readiness sha: `e4cad1336db37d08bfdaa2598948908a5b8baa15d75bf9fe8eb6d842e8c1ddee`.

PM also fixed `restart_all.sh` so future API restarts forward `BYBIT_MODE` and `BYBIT_CONNECTOR_WRITE_ENABLED` from `trading_services.env` into the API process.

Boundary: no secret output, no Bybit order/private call, no Decision Lease acquire, no order/cancel/modify, no Cost Gate change, no live/mainnet authorization, and no promotion proof. Next gate is fresh final-window BBO / Decision Lease / Guardian / Rust authority / GUI cap before any bounded Demo order.
