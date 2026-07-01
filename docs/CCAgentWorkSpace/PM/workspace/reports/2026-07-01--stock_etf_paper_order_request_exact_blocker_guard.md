# Stock/ETF Paper Order Request Exact Blocker Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR `stock_etf_cash` paper/shadow source-only acceptance hardening

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 補強 `StockEtfPaperOrderRequestEnvelopeV1` paper-order request envelope 的 aggregate
fail-closed coverage。它只改測試與 source-static guard，不改 Rust production validator、IPC、API route、
GUI runtime、connector、secret、DB 或 Bybit 行為。

## Scope

已完成：

- 在 `stock_etf_paper_order_request_acceptance.rs` 將 default envelope 固定為完整 ordered blocker vector，
  覆蓋 contract/source identity、lane/broker/env、request/account identity 與 unsupported method。
- 將 method/authority/effect mismatch、effect lifecycle hash gaps、preview effect/cancel-replace pollution、
  submit order-intent failures、market-order price/TIF mismatch、cancel submit-shape pollution、replace
  replacement-shape gaps、boundary regression cases 改成 exact ordered vectors 或 exact single-blocker assertions。
- 移除 paper-order request blocker 的 loose `has()` / `blockers.contains` helper；aggregate cases 現在會對
  missing、extra、duplicated 或 reordered blockers fail deterministically。
- 在 `test_stock_etf_paper_order_request_validation_source_static.py` 補 validator blocker emit-order guard，
  pin top-level、boundary flags、expected surface、preview/submit/cancel/replace、order-intent、hash、limit-price
  子 validator 的 source order。

## Verification

- Targeted rustfmt check：PASS。
- Stock/ETF paper-order request source static pytest：`14 passed`。
- Stock/ETF paper-order request Rust acceptance：`17 passed`。
- Full `cargo test -p openclaw_types --quiet`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- `git diff --check`：PASS。

## Boundary

未做也未授權：

- Rust production code change。
- IPC/API route behavior change。
- GUI runtime or lane selector authority change。
- IBKR contact、IBKR SDK import、socket/client construction。
- secret access/creation/serialization。
- connector runtime、broker session、paper order routing/cancel/replace execution。
- lifecycle writer、fill import、DB/evidence writer、scorecard writer、evidence clock。
- paper-shadow launch、release launch、tiny-live/live authorization。
- Linux runtime sync/restart。
- Bybit live/demo execution 行為變更。
