# 2026-07-01 — Stock/ETF Paper Order Validation Source Static Guard

## Scope

PM added a source-only structure guard for
`rust/openclaw_types/src/stock_etf_paper_order_request/validation.rs`.

This is not a runtime behavior change, not IBKR contact, not connector runtime wiring, not secret
access, not DB/evidence writer work, not paper order routing, and not a Bybit behavior change. It
only locks the existing paper order request validation contract for preview, submit, cancel, and
replace request shapes.

## Guard Added

- `tests/structure/test_stock_etf_paper_order_request_validation_source_static.py`

The guard requires the validation child module to keep:

- a 520-line governance cap and the existing helper/function surface;
- top-level fail-closed contract, source version, Stock/ETF cash lane, IBKR broker, paper-only
  environment, live-denial, boundary flag, and request-method dispatch checks;
- method-specific surface mapping: preview remains read-only and non-effect-capable, while
  submit/cancel/replace remain paper-rehearsal effect-capable;
- method-specific field separation for preview, submit, cancel, and replace requests;
- order shape, symbol, side, quantity, limit/market price, time-in-force, preview hash, and
  effect hash gates;
- no runtime, secret material, order client, or Bybit client tokens.

## Verification

- New validation guard py_compile: PASS.
- Focused new guard pytest: `6 passed`.
- Focused paper-order request validation/parent/fixtures/split subset: `20 passed`.
- Dynamic docs trace pytest: `2 passed, 5 deselected`; parsed checkpoint titles `130`, missing `[]`.
- Diff check: PASS.

## Boundary

No Rust production code changed. No endpoint, IPC method, connector, SDK import, socket/HTTP path,
secret access, read-only probe execution, result import, DB/evidence writer, paper order/cancel/
replace route, tiny-live/live authorization, Linux runtime sync/restart, or Bybit live/demo
execution behavior changed.
