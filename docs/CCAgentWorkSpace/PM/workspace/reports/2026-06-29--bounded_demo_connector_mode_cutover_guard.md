# 2026-06-29 bounded Demo connector-mode cutover guard

## Summary

本 checkpoint 收緊 bounded Demo credential/mode cutover：`POST /api/v1/settings/bybit-demo-connector-mode` 現在會拒絕仍含 `demo_api_slot:*` credential blocker 的 cutover preflight。這防止 Demo API slot 缺 key、缺 secret、endpoint 錯誤，或 strict expected-key pin 明確不匹配時，先把 connector 切成 `BYBIT_MODE=demo` / `BYBIT_CONNECTOR_WRITE_ENABLED=true`。

狀態轉移：`DONE_WITH_CONCERNS`，bounded Demo execution 仍是 `BLOCKED_BY_RUNTIME`。

## Source

- Source commit: `d9336342d3ee45467f456224eca278da14673956`
- Changed:
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/settings_routes.py`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_settings_bybit_demo_connector_mode.py`
  - `helper_scripts/research/cost_gate_learning_lane/bounded_demo_credential_mode_cutover_preflight.py`
  - `helper_scripts/research/tests/test_cost_gate_bounded_demo_credential_mode_cutover_preflight.py`

## Runtime Evidence

- Runtime HEAD: `d9336342d3ee45467f456224eca278da14673956`
- Crontab expected-head pins: `9`
- Control API: restarted only for source reload
- Engine: PID `877736`, not restarted
- New readiness:
  - `/tmp/openclaw/session_loop_state_20260629T203610Z_fast_demo_loop/bounded_demo_runtime_readiness_after_d933_guard.json`
  - sha `dfa4d1a02d45ba1cab46a4164b04bd0440a59bd31303d98e3684d50908ff5e02`
  - status `BOUNDED_DEMO_RUNTIME_BLOCKED_BY_CREDENTIALS`
- New cutover preflight:
  - `/tmp/openclaw/session_loop_state_20260629T203610Z_fast_demo_loop/bounded_demo_credential_mode_cutover_preflight_after_d933_guard.json`
  - sha `59cbd358e77ddc1fc7a3fe4427351cb4336e457f1d0142acad41dcc4235c37d6`
  - source check `connector_mode_requires_demo_credential_readiness=true`
- Runtime dry-run validator:
  - rejected current preflight with HTTP `400`
  - historical reason: `demo_api_slot:demo_api_key_expected_value_mismatch`
  - 2026-06-30 correction: this reason came from a stale `BHw4...` expected-key hint; masked `FWkGZX...g53T` is now operator-confirmed as the correct Demo key
  - `trading_services.env` unchanged: `BYBIT_MODE=read_only`, `BYBIT_CONNECTOR_WRITE_ENABLED=false`

## Verification

- Local `py_compile`: PASS
- Local cutover/readiness tests: `10 passed`
- Local settings API key + connector mode tests: `10 passed`
- Local adjacent learning lane suite: `48 passed`
- Local OpenAPI generation: `3.1.0 / 288`
- Local `git diff --check`: PASS
- Runtime `py_compile`: PASS
- Runtime cutover/readiness tests: `10 passed`
- Runtime settings API key + connector mode tests: `10 passed`
- Runtime HTTP `/openapi.json`: `3.1.0 / 288`

## Boundary

No engine restart, no key/secret output, no secret/env mutation, no private Bybit call, no credential validation request, no Decision Lease acquire/release, no order/cancel/modify, no PG/registry write, no model load, no Cost Gate lowering, no live/mainnet authority, and no promotion/profit proof.

## Remaining Blocker

Correction on 2026-06-30: Demo slot key `FWkGZX...g53T` / sha12 `317f982c009f` is operator-confirmed correct. The remaining blocker is connector mode (`BYBIT_MODE=read_only`, `BYBIT_CONNECTOR_WRITE_ENABLED=false`) plus fresh readiness/final-window gates. Rerun readiness without the stale `BHw4...` expected pin, then apply connector mode cutover only after credential/endpoint checks are green.
