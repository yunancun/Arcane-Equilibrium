# PM Checkpoint - IBKR Stock/ETF GUI Scorecard/Launch Renderer Split Guard

Date: 2026-07-01

Scope: Stock/ETF IBKR static GUI source hygiene only.

## Outcome

PM moved the Scorecard and Launch panel renderers from `tab-stock-etf.js` into
the new display-only module `tab-stock-etf-scorecard-launch.js`.

`tab-stock-etf.js` is reduced from `583` to `350` lines. The scorecard/launch
module is `281` lines and exposes `window.renderScorecardStatus` and
`window.renderLaunchStatus` to the main loader.

## Guards

- Static no-write guard scans `tab-stock-etf-scorecard-launch.js`.
- Static split guard proves the scorecard and launch renderers stay out of the
  main bundle.
- Main GUI bundle is capped at `<= 400` lines.
- Scorecard/launch child module is capped at `<= 500` lines.

## Verification

- Stock/ETF JS `node --check`: PASS.
- Route/no-write focused tests: `29 passed`.
- Full Stock/ETF FastAPI/static: `110 passed`.
- IBKR timeline + trace-title structure guard: `2 passed`.
- `git diff --check`: PASS.

## Boundary

No new endpoint, IPC method, client input, IBKR contact, SDK import,
socket/HTTP, connector runtime, secret access, read probe execution, paper
order, fill import, evidence writer, DB apply, evidence clock, tiny-live,
live, or Bybit behavior change.
