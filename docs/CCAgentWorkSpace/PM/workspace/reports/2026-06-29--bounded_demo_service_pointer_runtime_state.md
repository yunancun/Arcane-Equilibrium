# 2026-06-29 bounded Demo service-pointer runtime state

## Summary

本 checkpoint 修正 bounded Demo soak monitor 的 runtime service pointer：當前交易控制 API 的 user unit 是 `openclaw-trading-api.service`，不是 stale `tradebot-control-api.service`。這輪只做 read-only runtime inspection 與 TODO/docs pointer 更新；沒有 runtime mutation。

## Evidence

- Runtime date checked: `2026-06-29T20:56:18Z`
- Runtime source checkouts:
  - `/home/ncyu/BybitOpenClaw/srv` head `b5a30d2ebce221494efc02bbd41454bbbc7d26d5`, clean
  - `/home/ncyu/srv` head `b5a30d2ebce221494efc02bbd41454bbbc7d26d5`, clean
- Engine: PID `877736`, alive
- API: `openclaw-trading-api.service` active/running, MainPID `991615`
- Watchdog: `openclaw-watchdog.service` active/running, MainPID `845152`
- Stale unit check: `tradebot-control-api.service` is not a current user unit
- API probe: `http://100.91.109.86:8000/openapi.json` returned HTTP `200`
- Linux public IPv4: `79.117.10.224`

## Runtime Artifacts

- Readiness:
  - `/tmp/openclaw/session_loop_state_20260629T2056Z_goal_continuation/bounded_demo_runtime_readiness.json`
  - sha256 `6a108a8b32a3b73413a5fbc49455aae116986f259bb10ca2b0af60dc75b6a04f`
  - status `BOUNDED_DEMO_RUNTIME_BLOCKED_BY_CREDENTIALS`
- Service-pointer state:
  - `/tmp/openclaw/session_loop_state_20260629T2054Z_service_pointer_runtime/session_loop_state_service_pointer_runtime.json`
  - sha256 `0c8fee26c24884a90d08ded8aa283bb0d32a401be9bc4a8a7c0f5ee72adb2e0e`
  - status `DONE_WITH_CONCERNS`

## Blockers

- Demo API key still does not match operator-expected prefix:
  - observed masked key `FWkGZX...g53T`
  - observed sha12 `317f982c009f`
  - expected prefix check `BHw4...` is false
- Connector remains read-only:
  - `BYBIT_MODE=read_only`
  - `BYBIT_CONNECTOR_WRITE_ENABLED=false`
- Candidate-matched bounded Demo order/fill/fee/slippage/reconstruction evidence is still absent.

## Boundary

No runtime source sync/deploy, no engine/API restart, no secret/env mutation, no private Bybit call, no credential validation request, no Decision Lease acquire/release, no order/cancel/modify, no PG write, no model load, no Cost Gate lowering, no live/mainnet authority, and no promotion/profit proof.

## State Transition

`DONE_WITH_CONCERNS` / `BLOCKED_BY_RUNTIME`.

Next executable action: operator enters the expected Demo key+secret through approved settings API/GUI, then rerun bounded Demo readiness. Connector mode cutover must remain fail-closed while any `demo_api_slot:*` blocker remains.
