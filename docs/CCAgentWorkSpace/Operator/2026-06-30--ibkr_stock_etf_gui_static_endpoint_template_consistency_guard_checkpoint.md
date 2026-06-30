# Operator Brief - IBKR Stock/ETF GUI Static Endpoint Template Consistency Guard

Date: 2026-06-30

## Summary

PM added a source-only static GUI/template drift guard for Stock/ETF endpoints.

- Static `tab-stock-etf*` sources are scanned for `/api/v1/stock-etf...`
  endpoints.
- The discovered GUI endpoint set must equal
  `settings/broker/stock_etf_gui_lane_contract.template.toml` endpoint declarations.
- This complements the OpenAPI/template guard and prevents accidental GUI-only
  endpoint additions or stale GUI endpoint omissions.

## Verification

- Python no-write static guard: `5 passed`
- Full Stock/ETF FastAPI/static: `97 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`: PASS

## Boundary

No IBKR contact, SDK import, socket/HTTP, secret access/creation, connector
runtime, read probe execution, paper order/cancel/replace, fill import, evidence
writer, DB apply, evidence clock, tiny-live/live authority, or Bybit behavior
change.
