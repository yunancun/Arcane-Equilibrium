# 2026-07-01 Operator Brief - IBKR Stock/ETF GUI Data/Policy Renderer Split Guard

PM completed a second source-only Stock/ETF GUI structure checkpoint for the
data/policy panels.

- `renderDataFoundationStatus` and `renderPolicyStatus` now live in
  `tab-stock-etf-data-policy.js`.
- Main GUI bundle size is now `985` lines, down from `1244`.
- Data-policy module is `469` lines and remains capped below `700`.
- Static guard now prevents the data/policy renderers from returning to the main
  bundle.

Verification passed:

- Stock/ETF JS `node --check`
- Route/no-write focused tests: `26 passed`
- Full Stock/ETF FastAPI/static: `107 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`

Boundary unchanged: no IBKR contact, no broker SDK/network client, no connector
runtime, no secret access, no read probe execution, no paper order, no DB/evidence
writer, no tiny-live/live authority, and no Bybit behavior change.
