# PM Report — Stock/ETF Lane Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR Stock/ETF lane foundation source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_lane.rs` 的 lane foundation source-only 姿態；不是 feature flag
enablement、不是 Phase 2 runtime start、不是 IBKR contact、不是 paper-order
authority。

## Completed

- 新增 `tests/structure/test_stock_etf_lane_source_static.py`。
- Guard 要求 `stock_etf_lane.rs` 低於 800 行 governance cap。
- Guard 要求 lane/broker/environment/instrument/authority/operation/denial/gate/
  lifecycle type surface 保持在 source 中。
- Guard 要求 15 個 broker operation variants、20 個 denial variants、13 個 gate
  fields 保持完整，並保留 live/margin/options/CFD/account-write typed denials。
- Guard 將 feature flag env keys 限定為 5 個非 secret allowlist keys，且只允許
  `StockEtfFeatureFlags::from_env()` 的單一 `std::env::var(key).ok()` path。
- Guard 禁止 fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens 與
  secret/account material tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_lane_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_lane_source_static.py`：
  `4 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_lane_acceptance -- --nocapture`：
  `9 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、DB apply、evidence writer/clock、
scorecard writer、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
