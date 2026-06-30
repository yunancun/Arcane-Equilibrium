# PM Checkpoint - IBKR Stock/ETF GUI Authorization/Account Renderer Split Guard

Date: 2026-07-01

Scope: Stock/ETF IBKR static GUI source hygiene only.

## Outcome

PM moved the Authorization and Account panel renderers from `tab-stock-etf.js`
into the new display-only module `tab-stock-etf-auth-account.js`.

`tab-stock-etf.js` is reduced from `985` to `798` lines. The auth/account module
is `235` lines and exposes `window.renderAuthorizationStatus` and
`window.renderAccountStatus` to the main loader.

## Guards

- Static no-write guard scans `tab-stock-etf-auth-account.js`.
- Static split guard proves `renderAuthorizationStatus` and
  `renderAccountStatus` stay out of the main bundle.
- Main GUI bundle is capped at `<= 900` lines.
- Auth/account child module is capped at `<= 400` lines.

## Verification

- Stock/ETF JS `node --check`: PASS.
- Route/no-write focused tests: `27 passed`.
- Full Stock/ETF FastAPI/static: `108 passed`.
- IBKR timeline + trace-title structure guard: `2 passed`.
- `git diff --check`: PASS.

## Boundary

No new endpoint, IPC method, client input, IBKR contact, SDK import,
socket/HTTP, connector runtime, secret access, read probe execution, paper
order, fill import, evidence writer, DB apply, evidence clock, tiny-live,
live, or Bybit behavior change.
