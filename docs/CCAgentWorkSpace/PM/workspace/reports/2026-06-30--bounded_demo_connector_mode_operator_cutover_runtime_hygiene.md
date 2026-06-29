# Bounded Demo Connector Mode Operator Cutover + Runtime Hygiene

Date: 2026-06-30
Owner: PM
Runtime: `trade-core` `/home/ncyu/BybitOpenClaw/srv`

## Summary

Operator clarified that the Bybit Demo key masked `FWkGZX...g53T` is correct and explicitly authorized AE/API operations on Bybit Demo. PM treated that as Demo-only authorization, not live/mainnet authorization.

`BYBIT_MODE=read_only` was confirmed to be a local runtime connector gate, not a Bybit dashboard permission. PM applied the reviewed Demo connector-mode cutover through the approved Control API path, then fixed residual runtime hygiene so the active API service process also sees the new mode.

## Runtime Changes

- Approved settings route used: `POST /api/v1/settings/bybit-demo-connector-mode`.
- Persisted env file now has `BYBIT_MODE=demo` and `BYBIT_CONNECTOR_WRITE_ENABLED=true`.
- Runtime mainnet gate remains `OPENCLAW_ALLOW_MAINNET=0`.
- Engine restarted env-only with `--keep-auth`; new engine PID observed: `1036295`.
- A restart helper gap was found: manual `restart_all.sh --keep-auth` started an orphan uvicorn while `openclaw-trading-api.service` auto-restarted and failed on port `8000`.
- PM cleared the orphan uvicorn processes and reclaimed API ownership under `openclaw-trading-api.service`.
- Current API unit: active/running, MainPID `1038429`, `NRestarts=0`, `/openapi.json` `200`.
- Current watchdog unit: active/running, MainPID `845152`.

## Source Fix

`helper_scripts/restart_all.sh` now forwards `BYBIT_MODE` and `BYBIT_CONNECTOR_WRITE_ENABLED` from `trading_services.env` into the API process. This closes the gap where the file was correct but the settings route still reported `restart_required` because process env was missing.

Regression added in `tests/structure/test_restart_all_keep_auth_preflight_static.py`.

Verification:

- `bash -n helper_scripts/restart_all.sh`
- `python3 -m pytest tests/structure/test_restart_all_keep_auth_preflight_static.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_settings_bybit_demo_connector_mode.py -q`
- Local: `13 passed`
- Runtime hotfix verification: `13 passed`

## Evidence

Artifact directory:

`/tmp/openclaw/demo_connector_cutover_operator_auth_20260630T0018Z/`

Key artifacts:

- Preflight: `bounded_demo_credential_mode_cutover_preflight_after_operator_auth.json`, sha `a54ffc530b1938941521d26add1197dfed5ce6435ec964fae9c3024dec63f44b`
- Settings POST response: `bybit_demo_connector_mode_cutover_response.json`, sha `8172208bfcaca8dc24d9524a84a993efb9f0da4911f462c81e1daa350515bfe0`
- Settings GET after service reclaim: `bybit_demo_connector_mode_after_systemd_reclaim_get.json`, sha `1f25e50709259e4d71fb78f46704d509dac14722513b7b39980e0e3091eae311`
- Readiness after restart: `bounded_demo_runtime_readiness_after_connector_restart.json`, sha `e4cad1336db37d08bfdaa2598948908a5b8baa15d75bf9fe8eb6d842e8c1ddee`

Readiness result:

- `BOUNDED_DEMO_RUNTIME_READY_FOR_FINAL_WINDOW_GATES`
- Connector blockers: `[]`
- Demo API slot: READY, masked key `FWkGZX...g53T`, sha12 `317f982c009f`
- Engine env: READY with `OPENCLAW_ALLOW_MAINNET=0`, `OPENCLAW_ENABLE_PAPER=0`, writer and bounded probe adapter enabled
- Plan sha: `80ba57285f0a7f9d20ea0f4621660d1c917245f8b1bc33f95b534568a74b86a6`
- Standing auth sha: `8df714a98f0d193f239a4c35b584870275fd14429ed60be8bc6b4cc22db16acc`

Settings GET after reclaim:

- `configured_ready=True`
- `runtime_ready=True`
- `restart_required=False`
- runtime `BYBIT_MODE=demo`
- runtime `BYBIT_CONNECTOR_WRITE_ENABLED=true`

## Boundary

No API key/secret was printed. No secret write was performed in this step. No Bybit credential validation call, private Bybit/order call, Decision Lease acquire, order submit/cancel/modify, Cost Gate change, model load, registry write, or live/mainnet authorization occurred.

Connector mode is now ready for final-window gates. It is not promotion proof. Engine log after cutover still reports `fills=0`; observed order-capable attempts remained blocked by bounded-probe isolation until the dedicated final-window path is run.

## Next

Rerun current ETH final-window gates with fresh artifacts: BBO/instrument, runner-owned short Decision Lease, Guardian/Rust authority, GUI cap, auditability, and reconstructability. Promotion remains blocked until candidate-matched Demo fills with fees/slippage/control/reconstruction evidence exist.
