# 2026-07-01 Operator Brief - IBKR Stock/ETF GUI Evidence/Paper Renderer Split Guard

PM completed a source-only Stock/ETF GUI structure checkpoint for the
evidence/universe/shadow/paper panels.

- `renderEvidenceStatus`, `renderUniverseStatus`, `renderShadowStatus`, and
  `renderPaperStatus` now live in `tab-stock-etf-evidence-paper.js`.
- Main GUI bundle size is now `583` lines, down from `798`.
- Evidence/paper module is `265` lines and remains capped below `500`.
- Static guard now prevents these renderers from returning to the main bundle.

Verification passed:

- Stock/ETF JS `node --check`
- Route/no-write focused tests: `28 passed`
- Full Stock/ETF FastAPI/static: `109 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`

Boundary unchanged: no IBKR contact, no broker SDK/network client, no connector
runtime, no secret access, no read probe execution, no paper order, no DB/evidence
writer, no tiny-live/live authority, and no Bybit behavior change.
