# 2026-07-01 — Stock/ETF ADR/AMD Authority Coverage Static Guard

## Scope

PM added a source-only meta guard for the ADR-0048 and AMD-2026-06-29-01 authority artifacts.

This is not an ADR/AMD content change, not IBKR contact, not connector runtime wiring, not secret
access, not DB migration apply, not paper order routing, and not a Bybit behavior change. It only
locks that the highest-level authority documents remain directly referenced, launch-traced, and
fail closed around the Stock/ETF research lane boundary.

## Guard Added

- `tests/structure/test_stock_etf_authority_artifact_coverage_static.py`

The guard pins:

- the current Stock/ETF authority artifact set is exactly
  `docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md` and
  `docs/governance_dev/amendments/2026-06-29--AMD-2026-06-29-01-ibkr-stock-etf-paper-shadow-lane.md`;
- unrelated Bybit and multi-venue ADRs are not selected by this Stock/ETF authority scan;
- both authority artifacts are directly referenced by existing structure or Stock/ETF control-api
  tests outside this guard;
- the main IBKR Stock/ETF execution plan and Operator launch summary both list the full authority
  artifact paths;
- ADR-0048 keeps Bybit as the only active live execution venue, keeps IBKR within read-only /
  paper / shadow research scope, preserves closed lane/broker/environment taxonomy, and keeps the
  denied live/tiny-live/margin/short/options/CFD/transfer/GUI/Python/Bybit-paper-reuse paths;
- AMD-2026-06-29-01 keeps the paper/shadow amendment boundary, allowed readonly/paper secret slots,
  denied live slot, Rust authority, inert IBKR connector skeleton posture, and discussion-only
  tiny-live eligibility.

## Verification

- New structure guard py_compile: PASS.
- Focused new guard pytest: `7 passed`.
- Focused ADR/AMD + Phase0/release source-static subset: `29 passed`.
- Docs PM trace tests: PASS.
- Diff check: PASS.

## Boundary

No ADR/AMD content change, no IBKR SDK import, no socket/HTTP, no secret read or creation, no
connector runtime, no read-only probe, no result import, no DB apply, no paper order route, no
tiny-live/live authorization, and no Bybit live/demo execution change.
