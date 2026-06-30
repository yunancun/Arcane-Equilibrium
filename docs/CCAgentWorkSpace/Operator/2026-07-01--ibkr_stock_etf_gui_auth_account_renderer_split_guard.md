# 2026-07-01 Operator Brief - IBKR Stock/ETF GUI Authorization/Account Renderer Split Guard

PM completed a source-only Stock/ETF GUI structure checkpoint for the
authorization/account panels.

- `renderAuthorizationStatus` and `renderAccountStatus` now live in
  `tab-stock-etf-auth-account.js`.
- Main GUI bundle size is now `798` lines, down from `985`.
- Auth/account module is `235` lines and remains capped below `400`.
- Static guard now prevents these renderers from returning to the main bundle.

Verification passed:

- Stock/ETF JS `node --check`
- Route/no-write focused tests: `27 passed`
- Full Stock/ETF FastAPI/static: `108 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`

Boundary unchanged: no IBKR contact, no broker SDK/network client, no connector
runtime, no secret access, no read probe execution, no paper order, no DB/evidence
writer, no tiny-live/live authority, and no Bybit behavior change.
