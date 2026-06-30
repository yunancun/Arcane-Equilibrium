# PM Checkpoint - IBKR Stock/ETF GUI Readiness Renderer Split Guard

Date: 2026-07-01

Scope: Stock/ETF IBKR static GUI source hygiene only.

## Outcome

PM moved the lane/readiness boundary renderer and its local UI helpers from
`tab-stock-etf.js` into the new display-only module `tab-stock-etf-readiness.js`.

`tab-stock-etf.js` is reduced from `350` to `197` lines. The readiness module
is `159` lines and exposes `window.renderReadiness` to the main loader and
fallback path.

## Guards

- Static no-write guard scans `tab-stock-etf-readiness.js`.
- Static split guard proves `renderReadiness(data, laneStatus)` stays out of the
  main bundle.
- Helper definitions such as `toneFor` and `kvRow` stay out of the main bundle.
- Main GUI bundle is capped at `<= 250` lines.
- Readiness child module is capped at `<= 250` lines.

## Verification

- Stock/ETF JS `node --check`: PASS.
- Route/no-write focused tests: `30 passed`.
- Full Stock/ETF FastAPI/static: `111 passed`.
- IBKR timeline + trace-title structure guard: `2 passed`.
- `git diff --check`: PASS.

## Boundary

No new endpoint, IPC method, client input, IBKR contact, SDK import,
socket/HTTP, connector runtime, secret access, read probe execution, paper
order, fill import, evidence writer, DB apply, evidence clock, tiny-live,
live, or Bybit behavior change.
