# PM Report — Stock/ETF Paper Order Request Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF paper order request envelope semantic source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_paper_order_request.rs` 與 validation module 的 source-only 姿態；不是
IPC runtime、不是 IBKR contact、不是 connector start、不是 paper order route。

## Completed

- 新增 `tests/structure/test_stock_etf_paper_order_request_source_static.py`。
- Guard 要求 parent module 與 validation module 低於 800 行 governance cap。
- Guard 要求 request envelope fields、paper order type/time-in-force/limit-price policy、
  verdict/blocker surface 與 validation helper surface 保持在 source 中。
- Guard 要求 default 仍 fail-closed：CryptoPerp/Bybit、LiveReservedDenied、
  UnknownDenied IPC method、TransferOrAccountWrite operation、Denied authority、
  `effect_capable=false`，且 no contact/runtime/secret/order/Bybit/live flags。
- Guard 要求 preview 仍是 `PaperOrderSubmit` + ReadOnly + effect=false；submit/cancel/
  replace 仍是 PaperRehearsal + effect=true，並保持 operation/scope/effect mismatch
  blockers。
- Guard 要求 request id、account/session/scoped-auth/guardian/lifecycle/broker-capability
  hashes、decision lease、audit event、risk/instrument/cost/universe/source artifact hashes
  checks 不得消失。
- Guard 要求 submit/preview order intent 仍限制 normalized symbol、Buy/Sell side、
  Stock/ETF instrument、positive quantity、limit/market price policy 與 TIF compatibility。
- Guard 要求 preview 禁止 effect/lifecycle fields，submit 禁止 broker order id 與
  cancel/replace fields，cancel 禁止 order-shape pollution，replace 禁止 original mutable
  fields。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_paper_order_request_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_paper_order_request_source_static.py`：
  `5 passed`。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_paper_order_request_split_static.py tests/structure/test_stock_etf_paper_order_request_source_static.py`：
  `8 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_paper_order_request_acceptance -- --nocapture`：
  `8 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、DB apply、evidence writer/clock、
scorecard writer、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
