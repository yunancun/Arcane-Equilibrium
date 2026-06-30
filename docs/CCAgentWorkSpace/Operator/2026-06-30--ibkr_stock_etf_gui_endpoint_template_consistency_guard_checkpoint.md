# Operator Brief - IBKR Stock/ETF GUI Endpoint Template Consistency Guard

Date: 2026-06-30

## Summary

PM added a source-only drift guard between FastAPI OpenAPI and the GUI lane
contract template for Stock/ETF status endpoints.

- OpenAPI Stock/ETF GET paths must match
  `settings/broker/stock_etf_gui_lane_contract.template.toml` endpoint declarations.
- Root redirect `/api/v1/stock-etf` is excluded because it is not a status
  endpoint in `gui_lane_contract_v1`.
- Numeric endpoint keys such as `phase0_status_endpoint` are covered.

## Verification

- Stock/ETF route tests: `11 passed`
- Full Stock/ETF FastAPI/static: `96 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`: PASS

## Boundary

No IBKR contact, SDK import, socket/HTTP, secret access/creation, connector
runtime, read probe execution, paper order/cancel/replace, fill import, evidence
writer, DB apply, evidence clock, tiny-live/live authority, or Bybit behavior
change.
