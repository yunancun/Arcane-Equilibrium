# 2026-07-01 — Stock/ETF Index Reference Integrity Static Guard

## Scope

PM added a source-only guard for IBKR/Stock-ETF references in the document and initiative indexes.

This is not an index wording change, not IBKR contact, not connector runtime wiring, not secret
access, not DB migration apply, not paper order routing, and not a Bybit behavior change. It only
locks that index-level launch trace links for the IBKR Stock/ETF lane point at existing files.

## Guard Added

- `tests/structure/test_stock_etf_index_reference_integrity_static.py`

The guard pins:

- `docs/_indexes/document_index.md` and `docs/_indexes/initiative_index.md` exist;
- IBKR/Stock-ETF code spans in both indexes are scanned for path-like references;
- path-like references under `docs/`, `settings/`, ADR, governance amendment, execution plan, and
  CCAgent workspace prefixes resolve to existing repo files;
- expected non-path code spans such as `/api/v1/stock-etf/readiness`,
  `first_ibkr_contact_allowed=false`, and `stock_etf.*` are intentionally not treated as files;
- required launch trace references remain present for ADR-0048, AMD-2026-06-29-01, Phase0 packet
  artifacts, DB DDL source draft, the main execution plan, PM round3 report, and Operator round3
  summary.

## Verification

- New structure guard py_compile: PASS.
- Focused new guard pytest: `3 passed`.
- Focused index + stable-boundary + ADR/AMD + Phase0 spec artifact subset: `19 passed`.
- Docs PM trace tests: PASS.
- Diff check: PASS.

## Boundary

No index wording change, no IBKR SDK import, no socket/HTTP, no secret read or creation, no
connector runtime, no read-only probe, no result import, no DB apply, no paper order route, no
tiny-live/live authorization, and no Bybit live/demo execution change.
