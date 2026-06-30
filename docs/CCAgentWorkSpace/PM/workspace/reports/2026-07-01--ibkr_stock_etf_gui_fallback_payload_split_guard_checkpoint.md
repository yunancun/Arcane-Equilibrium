# PM Checkpoint - IBKR Stock/ETF GUI Fallback Payload Split Guard

Date: 2026-07-01

Scope: Stock/ETF IBKR static GUI source hygiene only.

## Outcome

PM split the remaining large display-only fallback payload builders out of
`tab-stock-etf.js` into `tab-stock-etf-fallbacks.js`.

Moved fallback builders:

- `authorizationFallback`
- `accountFallback`
- `evidenceFallback`
- `universeFallback`
- `shadowFallback`
- `paperFallback`
- `scorecardFallback`
- `launchFallback`

`tab-stock-etf.js` is reduced from `1805` to `1244` lines. The new fallback
module is `563` lines and is loaded before the main Stock/ETF tab loader.

## Guards

- Stock/ETF static no-write guard now scans `tab-stock-etf-fallbacks.js`.
- The guard proves the moved fallback builders stay out of the main bundle.
- The guard caps `tab-stock-etf.js <= 1400` and
  `tab-stock-etf-fallbacks.js <= 800`.
- The readonly static route test now includes data-policy and fallback child
  modules when checking display-only evidence tokens.

## Verification

- Stock/ETF JS `node --check`: PASS.
- Route/no-write focused tests: `25 passed`.
- Full Stock/ETF FastAPI/static: `106 passed`.
- IBKR timeline + trace-title structure guard: `2 passed`.
- `git diff --check`: PASS.

## Boundary

No new endpoint, IPC method, client input, IBKR contact, SDK import,
socket/HTTP, connector runtime, secret access, read probe execution, paper
order, fill import, evidence writer, DB apply, evidence clock, tiny-live,
live, or Bybit behavior change.
