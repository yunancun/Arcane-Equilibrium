# PM Checkpoint - IBKR Stock/ETF GUI Data/Policy Renderer Split Guard

Date: 2026-07-01

Scope: Stock/ETF IBKR static GUI source hygiene only.

## Outcome

PM moved the Data Foundation and Policy panel renderers from `tab-stock-etf.js`
into `tab-stock-etf-data-policy.js`.

`tab-stock-etf.js` is reduced from `1244` to `985` lines. The data-policy module
is now `469` lines and owns both fallback payload builders and renderers for the
Data Foundation / Policy panels.

## Guards

- Static no-write guard proves `renderDataFoundationStatus` and
  `renderPolicyStatus` stay out of the main bundle.
- The main GUI bundle is capped at `<= 1100` lines.
- The data-policy child module is capped at `<= 700` lines.
- The full Stock/ETF static bundle remains covered by no-write, endpoint, and
  display-only route tests.

## Verification

- Stock/ETF JS `node --check`: PASS.
- Route/no-write focused tests: `26 passed`.
- Full Stock/ETF FastAPI/static: `107 passed`.
- IBKR timeline + trace-title structure guard: `2 passed`.
- `git diff --check`: PASS.

## Boundary

No new endpoint, IPC method, client input, IBKR contact, SDK import,
socket/HTTP, connector runtime, secret access, read probe execution, paper
order, fill import, evidence writer, DB apply, evidence clock, tiny-live,
live, or Bybit behavior change.
