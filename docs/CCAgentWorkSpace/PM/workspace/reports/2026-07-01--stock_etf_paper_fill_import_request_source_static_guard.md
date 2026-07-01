# PM Report — Stock/ETF Paper Fill Import Request Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF paper fill import request source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_paper_fill_import_request.rs` 的 source-only 姿態；不是 IBKR contact、
不是 connector construction、不是 fill import execution、不是 DB apply、不是 paper
order route。

## Completed

- 新增 `tests/structure/test_stock_etf_paper_fill_import_request_source_static.py`。
- Guard 要求 `stock_etf_paper_fill_import_request.rs` 低於 800 行 governance cap。
- Guard 要求 fill-import contract id、request/verdict/blocker surface、required-field
  validator、boundary-flag validator 與 lifecycle/event-log/redaction imports 保持在
  source 中。
- Guard 要求 default 仍 fail-closed：CryptoPerp/Bybit、LiveReservedDenied、
  UnknownDenied IPC method、TransferOrAccountWrite operation、Denied authority、
  `effect_capable=false`、observed state/stale policy empty。
- Guard 要求 accepted fixture 仍是 StockEtfCash/IBKR/Paper、ImportPaperFills、
  PaperOrderFillImport、ReadOnly、effect=false，並綁定 lifecycle/event-log/redaction
  contract ids、Filled observed state、PreserveTerminalWithEvidence stale policy。
- Guard 要求 request id、session attestation、lifecycle/event-log/redaction/source
  artifact hashes、reconciliation run id、broker order id、execution id、commission report id、
  import idempotency key、raw/redacted hashes checks 不得消失。
- Guard 要求 duplicate import denial、StateUnknown stale-policy handling、IBKR contact、
  connector runtime、secret serialization、fill import、DB apply、order route、Bybit reuse、
  live/tiny-live、margin/short/options/CFD、Python direct broker write boundary flags 不得消失。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_paper_fill_import_request_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_paper_fill_import_request_source_static.py`：
  `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_paper_fill_import_request_acceptance -- --nocapture`：
  `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import execution、DB apply、evidence
writer/clock、scorecard writer、GUI fanout、tiny-live/live、或任何 Bybit behavior
change。
