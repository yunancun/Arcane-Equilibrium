# PM Report — IBKR Phase2 Runtime Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR Phase 2 runtime-evidence source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`ibkr_phase2_runtime.rs` 的 source-only 姿態；不是 secret-slot reader、不是
gateway/TWS process start、不是 API topology probe、不是 IBKR contact。

## Completed

- 新增 `tests/structure/test_ibkr_phase2_runtime_source_static.py`。
- Guard 要求 `ibkr_phase2_runtime.rs` 低於 800 行 governance cap。
- Guard 要求 secret-slot / API-session-topology contract IDs、paper/live port
  imports、secret-slot posture enum、gateway process mode、verdict/blocker types 保持
  在 source 中。
- Guard 要求 secret-slot source template 維持 hashed paper slot、absent live slot、
  owner-only permission、env fallback denied、secret/account serialization false。
- Guard 要求 API session topology 維持 `ib_gateway_tws_api`、`trade-core`、
  loopback `127.0.0.1`、paper gateway port、PaperGateway mode、Paper environment、
  live-port denial 與 loopback check。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_ibkr_phase2_runtime_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_phase2_runtime_source_static.py`：
  `4 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test ibkr_phase2_runtime_acceptance -- --nocapture`：
  `7 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、DB apply、evidence writer/clock、
scorecard writer、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
