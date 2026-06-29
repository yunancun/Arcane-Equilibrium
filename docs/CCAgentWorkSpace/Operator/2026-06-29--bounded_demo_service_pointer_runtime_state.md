# 2026-06-29 bounded Demo service-pointer runtime state

## Operator Summary

這不是 engine 掛掉。當前活著的 user service 是：

- `openclaw-trading-api.service` active/running, MainPID `991615`
- `openclaw-watchdog.service` active/running, MainPID `845152`
- engine PID `877736`

舊檢查名 `tradebot-control-api.service` 是 stale pointer；它 not-found/dead 不代表 API 壞掉。API 在 `100.91.109.86:8000` 回 `/openapi.json` HTTP `200`。

## Current Blocker

bounded Demo 仍卡在 credentials/mode：

- Demo key masked `FWkGZX...g53T`, sha12 `317f982c009f`
- operator 期望 prefix `BHw4...`，目前不匹配
- `BYBIT_MODE=read_only`
- `BYBIT_CONNECTOR_WRITE_ENABLED=false`

Linux public IPv4 for Bybit allowlist: `79.117.10.224`.

## Latest Evidence

- readiness artifact: `/tmp/openclaw/session_loop_state_20260629T2056Z_goal_continuation/bounded_demo_runtime_readiness.json`
- readiness sha256: `6a108a8b32a3b73413a5fbc49455aae116986f259bb10ca2b0af60dc75b6a04f`
- service-pointer artifact: `/tmp/openclaw/session_loop_state_20260629T2054Z_service_pointer_runtime/session_loop_state_service_pointer_runtime.json`
- service-pointer sha256: `0c8fee26c24884a90d08ded8aa283bb0d32a401be9bc4a8a7c0f5ee72adb2e0e`

## Safety Boundary

本輪沒有重啟、沒有改 key/env、沒有打 Bybit private API、沒有拿 Decision Lease、沒有下單、沒有改 Cost Gate、沒有 live/mainnet。

State transition: `DONE_WITH_CONCERNS` / `BLOCKED_BY_RUNTIME`.
