# PM Report — Stock/ETF Lane-Scoped IPC Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR Stock/ETF lane-scoped IPC source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_lane_scoped_ipc.rs` 的 source-only 姿態；不是 IPC runtime start、不是
IBKR contact、不是 connector wiring，也不是 Bybit runtime reuse。

## Completed

- 新增 `tests/structure/test_stock_etf_lane_scoped_ipc_source_static.py`。
- Guard 要求 `stock_etf_lane_scoped_ipc.rs` 低於 800 行 governance cap。
- Guard 要求 20 個 lane-scoped IPC method variants 與 engine Method mapping 保持
  對齊。
- Guard 要求 `BybitSubmitPaperOrderDenied` / `UnknownDenied` denied sentinels 與
  lane IPC、scoped authorization、Phase2 gate、session attestation、non-Bybit
  allowlist、secret topology、broker registry、asset-lane events contract tokens 保持
  在 source 中。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime
  tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_lane_scoped_ipc_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_lane_scoped_ipc_source_static.py`：
  `3 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_lane_scoped_ipc_acceptance -- --nocapture`：
  `9 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、DB apply、evidence writer/clock、
scorecard writer、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
