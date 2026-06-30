# Operator Brief - IBKR Stock/ETF GUI Data/Policy Fallback Split Guard

Date: 2026-06-30

## Summary

PM split the large Data Foundation / Policy fallback payloads out of the main
Stock/ETF GUI bundle.

- `tab-stock-etf.js` is now `1805` lines, down from `1976`.
- New `tab-stock-etf-data-policy.js` carries only fallback payloads.
- All Stock/ETF GUI bundle files are below the 2000-line governance cap.
- The static guard now scans the new JS file and enforces that cap.

## Verification

- Stock/ETF JS `node --check`: PASS
- Python no-write/static guard: `10 passed`
- Full Stock/ETF FastAPI/static: `105 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`: PASS

## Boundary

No new endpoint, IBKR contact, SDK import, socket/HTTP, secret access/creation,
connector runtime, read probe execution, paper order/cancel/replace, fill import,
evidence writer, DB apply, evidence clock, tiny-live/live authority, or Bybit
behavior change.
