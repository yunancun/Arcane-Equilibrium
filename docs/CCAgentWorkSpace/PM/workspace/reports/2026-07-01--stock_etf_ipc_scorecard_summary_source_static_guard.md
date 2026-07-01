# 2026-07-01 — Stock/ETF IPC Scorecard Summary Source Static Guard

## Scope

PM added a source-only structure guard for
`rust/openclaw_engine/src/ipc_server/handlers/stock_etf/status_summaries/scorecard.rs`.

This is not an IPC runtime change, not a scorecard writer, not DB apply, not evidence-clock
runtime, not IBKR contact, not connector runtime, not paper order execution, and not a Bybit
behavior change. The checkpoint only hardens the display-only scorecard status child module that
was split below `status_summaries.rs`.

## Guard Added

- `tests/structure/test_stock_etf_ipc_scorecard_summary_source_static.py`

The guard pins:

- the `scorecard_status_summary(phase2)` display-only entry point;
- default construction and validation of `StockEtfScorecardInputBundleV1`,
  `StockEtfScorecardDerivationV1`, and `StockEtfScorecardVerdictV1`;
- blocked Phase 3 scorecard status posture with no writer, DB apply, evidence clock, order route,
  IBKR call, secret slot touch, Bybit IPC reuse, live, or tiny-live authority;
- scorecard input bundle lineage for read-only probe result import, market-data provenance,
  reference data, risk policy, atomic fact inputs, source commit, and separation flags;
- derivation and verdict lineage, PnL/cost/statistical fields, quality labels, review hashes, and
  sealed/default-blocked posture;
- absence of env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens and secret
  material access tokens.

## Verification

- New structure guard py_compile: PASS.
- Focused structure guard pytest: `5 passed`.
- Focused Rust IPC scorecard status acceptance: PASS.
- Existing Rust IPC handler split guard: PASS.
- Full `cargo test -p openclaw_engine`: PASS.
- Diff check: PASS.

## Boundary

No IBKR SDK import, no socket/HTTP, no secret read or creation, no connector runtime, no IPC runtime
side effect, no scorecard writer, no evidence-clock runtime, no DB apply, no paper order route or
paper submit/cancel/replace, no tiny-live/live authorization, and no Bybit live/demo execution
change.
