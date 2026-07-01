# 2026-07-01 — Stock/ETF Stable Boundary Docs Static Guard

## Scope

PM added a source-only guard for the stable boundary docs required by AMD-2026-06-29-01.

This is not a stable-doc wording change, not IBKR contact, not connector runtime wiring, not secret
access, not DB migration apply, not paper order routing, and not a Bybit behavior change. It only
locks that long-lived entry documents continue to distinguish active Bybit live execution from the
IBKR Stock/ETF paper/shadow research lane.

## Guard Added

- `tests/structure/test_stock_etf_stable_boundary_docs_static.py`

The guard pins:

- `CLAUDE.md`, `.codex/MEMORY.md`, `README.md`, `docs/_indexes/document_index.md`,
  `docs/_indexes/initiative_index.md`, and
  `docs/governance_dev/SPECIFICATION_REGISTER.md` all exist;
- CLAUDE/Codex memory keep the Bybit-only active live execution boundary and the ADR-0048 /
  AMD-2026-06-29-01 IBKR read-only/paper/shadow exception;
- README keeps the operator-facing statement that IBKR `stock_etf_cash` is not live/tiny-live or
  durable-alpha promotion evidence;
- document and initiative indexes keep direct routing to ADR-0048, AMD-2026-06-29-01, the Phase0
  packet, and the current blocker that real secret/topology evidence plus immutable Phase2 PASS
  artifact are still required;
- the governance specification register keeps the active amendment and ADR rows, Bybit-only live
  execution wording, IBKR read-only/paper/shadow limits, and the live/tiny-live/margin/short/options
  /CFD/transfer/account-write denials;
- stable docs do not claim IBKR live approval, connector runtime approval, paper-order route
  approval, or first-contact allowance.

## Verification

- New structure guard py_compile: PASS.
- Focused new guard pytest: `3 passed`.
- Focused stable-boundary + ADR/AMD + Phase0 spec artifact subset: `16 passed`.
- Docs PM trace tests: PASS.
- Diff check: PASS.

## Boundary

No stable-doc wording change, no IBKR SDK import, no socket/HTTP, no secret read or creation, no
connector runtime, no read-only probe, no result import, no DB apply, no paper order route, no
tiny-live/live authorization, and no Bybit live/demo execution change.
