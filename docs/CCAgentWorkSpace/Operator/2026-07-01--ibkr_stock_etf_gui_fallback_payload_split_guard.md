# 2026-07-01 Operator Brief - IBKR Stock/ETF GUI Fallback Payload Split Guard

PM completed a source-only Stock/ETF GUI structure checkpoint.

- `tab-stock-etf.js` fallback payload builders were split into
  `tab-stock-etf-fallbacks.js`.
- Main GUI bundle size is now `1244` lines, down from `1805`.
- New fallback module is `563` lines and is loaded before the main loader.
- Static guard now scans the new module and prevents the moved builders from
  returning to the main bundle.

Verification passed:

- Stock/ETF JS `node --check`
- Route/no-write focused tests: `25 passed`
- Full Stock/ETF FastAPI/static: `106 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`

Boundary unchanged: no IBKR contact, no broker SDK/network client, no connector
runtime, no secret access, no read probe execution, no paper order, no DB/evidence
writer, no tiny-live/live authority, and no Bybit behavior change.
