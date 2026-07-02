# Stock/ETF Paper Order Request Acceptance Split Guard

Date: 2026-07-02
Owner: PM
Mode: source/test-only checkpoint

## Summary

PM split the oversized paper-order request Rust acceptance file into focused integration tests by contract boundary:

- `stock_etf_paper_order_request_acceptance.rs` keeps default/accepted fixture, aggregate cross-wire, method-specific shape, boundary regression, and template coverage.
- `stock_etf_paper_order_request_gap_acceptance.rs` now owns the independent gap matrix coverage.

The split preserves the same 17 paper-order request tests and brings both files below the review hygiene threshold: 378 / 506 lines.

## Verification

- Changed-file rustfmt: PASS.
- Paper-order focused Rust acceptance: original `11 passed`, gap `6 passed`.
- Full `cargo test -p openclaw_types`: PASS.
- Test-count scan: PASS, 17 paper-order request tests after split.
- Line-count scan: PASS, both split files below 800 lines.

## Dispatch

PM did not dispatch PA/E1/E2/E4/QA for this checkpoint because it is a narrow test-file split with no production code, runtime path, exchange-facing behavior, or validator semantics change.

## Boundary

No Rust production code change, paper-order request validator semantics change, source/runtime config change, Rust IPC handler behavior change, FastAPI route behavior change, GUI behavior change, connector production code change, IBKR contact, connector runtime, socket/client construction, secret access, broker session, read-only probe execution, paper order routing/cancel/replace execution, fill import execution, release launch, DB/evidence writer, scorecard writer, evidence clock, destructive DB cleanup, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior change.
