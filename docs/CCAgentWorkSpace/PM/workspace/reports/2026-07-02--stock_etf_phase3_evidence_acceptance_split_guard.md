# Stock/ETF Phase3 Evidence Acceptance Split Guard

Date: 2026-07-02
Owner: PM
Mode: source/test-only checkpoint

## Summary

PM split the oversized Phase3 evidence Rust acceptance file into focused integration tests by contract boundary:

- `stock_etf_phase3_evidence_acceptance.rs` keeps collector run, evidence-clock day, and full Phase3 template coverage.
- `stock_etf_phase3_market_data_acceptance.rs` now owns market-data provenance and frozen-input coverage.
- `stock_etf_phase3_dq_acceptance.rs` now owns DQ manifest coverage.

The split preserves the same 24 Phase3 evidence-related tests and brings all three files below the review hygiene threshold: 640 / 265 / 173 lines.

## Verification

- Changed-file rustfmt: PASS.
- Phase3 focused Rust acceptance: DQ `5 passed`, evidence `11 passed`, market-data `8 passed`.
- Full `cargo test -p openclaw_types`: PASS.
- Test-count scan: PASS, 24 Phase3 evidence-related tests after split.
- Line-count scan: PASS, all split files below 800 lines.

Toolchain note: desktop shell `~/.cargo/bin` proxies point at a stale rustup-init symlink, so PM ran verification through Homebrew rustup plus the stable toolchain bin for this checkpoint. No repo, global toolchain, or global environment mutation was performed.

## Dispatch

PM did not dispatch PA/E1/E2/E4/QA for this checkpoint because it is a narrow test-file split with no production code, runtime path, exchange-facing behavior, or validator semantics change.

## Boundary

No Rust production code change, Phase3 validator semantics change, source/runtime config change, Rust IPC handler behavior change, FastAPI route behavior change, GUI behavior change, connector production code change, IBKR contact, connector runtime, socket/client construction, secret access, broker session, read-only probe execution, paper order routing/cancel/replace execution, fill import execution, release launch, DB/evidence writer, scorecard writer, evidence clock, destructive DB cleanup, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior change.
