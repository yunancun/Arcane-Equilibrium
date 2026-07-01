# PM Report — Stock/ETF Broker Capability Registry Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF IBKR broker capability registry source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_broker_capability_registry.rs` 的 source-only 姿態；不是 broker registry
activation、不是 IBKR contact、不是 read probe、不是 paper order authorization。

## Completed

- 新增 `tests/structure/test_stock_etf_broker_capability_registry_source_static.py`。
- Guard 要求 `stock_etf_broker_capability_registry.rs` 低於 800 行 governance cap。
- Guard 要求 registry contract id、audit fields、15 個 required operations、registry
  entry/verdict/blocker surface、expected capability mapper、entry validator 保持在
  source 中。
- Guard 要求 default 仍 fail-closed：CryptoPerp/Bybit、empty operations、Bybit live
  protection false、Python broker write denied false、IBKR live denied false。
- Guard 要求 accepted fixture 仍為 StockEtfCash/IBKR，並保留 Bybit live unchanged、
  Python broker write denied、IBKR live denied、CFD/margin reserved denied、no first
  IBKR contact、no secret serialization。
- Guard 要求 read-only rows 保留 external surface、lane-scoped IPC、readonly probe
  request、session/provenance/instrument gates；paper-write rows 保留 PaperRehearsal、
  paper attestation、scoped authorization、risk policy、decision lease、guardian 與
  lifecycle gates，且 Rust-owned。
- Guard 要求 shadow/scorecard rows 保留 evidence clock、PIT universe、strategy、
  reference/cost/provenance/cash-ledger/result-import gates。
- Guard 要求 live/margin/options/CFD/account-write rows 維持 Denied scope 與 typed
  denials。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_broker_capability_registry_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_broker_capability_registry_source_static.py`：
  `5 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_broker_capability_registry_acceptance -- --nocapture`：
  `10 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、DB apply、evidence writer/clock、
scorecard writer、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
