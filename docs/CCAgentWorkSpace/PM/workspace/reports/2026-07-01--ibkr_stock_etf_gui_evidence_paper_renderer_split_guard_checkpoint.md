# PM Checkpoint - IBKR Stock/ETF GUI Evidence/Paper Renderer Split Guard

Date: 2026-07-01

Scope: Stock/ETF IBKR static GUI source hygiene only.

## Outcome

PM moved the Evidence, Universe, Shadow, and Paper panel renderers from
`tab-stock-etf.js` into the new display-only module
`tab-stock-etf-evidence-paper.js`.

`tab-stock-etf.js` is reduced from `798` to `583` lines. The evidence/paper
module is `265` lines and exposes `window.renderEvidenceStatus`,
`window.renderUniverseStatus`, `window.renderShadowStatus`, and
`window.renderPaperStatus` to the main loader.

## Guards

- Static no-write guard scans `tab-stock-etf-evidence-paper.js`.
- Static split guard proves the evidence, universe, shadow, and paper renderers
  stay out of the main bundle.
- Main GUI bundle is capped at `<= 650` lines.
- Evidence/paper child module is capped at `<= 500` lines.

## Verification

- Stock/ETF JS `node --check`: PASS.
- Route/no-write focused tests: `28 passed`.
- Full Stock/ETF FastAPI/static: `109 passed`.
- IBKR timeline + trace-title structure guard: `2 passed`.
- `git diff --check`: PASS.

## Boundary

No new endpoint, IPC method, client input, IBKR contact, SDK import,
socket/HTTP, connector runtime, secret access, read probe execution, paper
order, fill import, evidence writer, DB apply, evidence clock, tiny-live,
live, or Bybit behavior change.
