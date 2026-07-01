# Control API Auth Source Repaired Fast Balance Ready

- Date: 2026-07-01
- Active blocker: `P0-CURRENT-CANDIDATE-CONTROL-API-AUTH-REPAIR-FOR-NOORDER-REFRESH`
- Next blocker: `P0-CURRENT-CANDIDATE-NOORDER-REFRESH-CURRENT-HEAD-E3-BB-REQUEST`
- State transition: `DONE_WITH_CONCERNS`
- Candidate: `grid_trading|ETHUSDT|Buy`

PM diagnosed the v710 Control API `401` without exposing token contents. No-secret metadata `/tmp/openclaw/session_loop_state_20260701T_control_api_auth_metadata_current_head_586583d/control_api_auth_source_metadata_no_secret.json` sha `f32aa0989c91e5dcc906fd2a6d5479bce41d16a182c41cf3be8a7ee259f95cb0` showed the runtime API process uses the default `0600` Control API token file candidate, while Mac and runtime token files are separate local files.

E3 approved only exact request `/tmp/openclaw/session_loop_state_20260701T_control_api_auth_metadata_current_head_586583d/runtime_local_fast_balance_e3_review_request.json` sha `db550e0825d68a065d48fe83e42bc485b7e6daee9ad90f6a7b205a0d9ecd594d`, with the added condition that PM prove `fast=1` would stay on the Rust snapshot branch before any GET. PM produced fast-branch preflight `/tmp/openclaw/session_loop_state_20260701T_control_api_auth_metadata_current_head_586583d/fast_balance_rust_snapshot_branch_preflight.json` sha `a0c0f7b7b2479e0ccf952a902c09de2dff45f4be91edcfce2366ab76c3af7ec8`: runtime `pipeline_snapshot_demo.json` was fresh, `trading_mode=demo`, and `paper_state` had a positive balance.

PM then executed exactly one runtime-local authenticated Control API GET to `/api/v1/strategy/demo/balance?fast=1` using the runtime token file through a temporary `0600` curl config removed by trap. Sanitized meta `/tmp/openclaw/session_loop_state_20260701T_control_api_auth_metadata_current_head_586583d/runtime_local_fast_balance_get_meta_sanitized.json` sha `c2fde84368cc0b83e48b3da628573e087176a8c5a7bdcb552fb2a266019248ca` records HTTP `200`, curl rc `0`, request count `1`, `read_model=rust_snapshot_fast`, `pipeline_status=connected`, and no token value/hash/prefix/suffix.

Using current-head source only in supplied-json mode, PM generated `/tmp/openclaw/session_loop_state_20260701T_control_api_auth_metadata_current_head_586583d/demo_account_equity_artifact_current_head_from_runtime_response.json` sha `db0c68bf028df42429d92583306b5ca8b0d5dd51b17661c2240dbf11b4ea16a4`, status `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`, equity `9541.87588778 USDT`.

No public Bybit quote, private/order endpoint, Control API POST, no-order envelope rebuild, plan-inclusion preview, canonical plan write, `_latest`, Decision Lease acquire/release, PG write, service/env/risk mutation, Cost Gate change, live/mainnet action, order/cancel/modify, fill, PnL, or profit proof occurred.

Final session state: `/tmp/openclaw/session_loop_state_20260701T_control_api_auth_metadata_current_head_586583d/session_loop_state_final.json` sha `ea523777faabf9ee48a1590d97d42d94a8f2f5d4f56cc24fd4d5c9b2cc043afb`.

Next action: generate a fresh current-head `PM -> E3 -> BB -> PM` no-order refresh request that consumes the v711 equity artifact and explicitly scopes any public Demo quote before running it.
