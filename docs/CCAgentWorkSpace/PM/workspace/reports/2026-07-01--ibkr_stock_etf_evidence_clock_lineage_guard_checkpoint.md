# PM Checkpoint Report — IBKR Stock/ETF Evidence Clock Lineage Guard

Date: 2026-07-01
Status: DONE_WITH_CONCERNS

## Summary

This checkpoint hardens the source-only `stock_etf_evidence_clock_v1` checker so
future evidence-clock day artifacts must carry collector-run and DQ-manifest
lineage. It does not start the evidence clock, write evidence, write scorecards,
contact IBKR, or change Bybit behavior.

## Changes

- Added collector-run contract id/hash and DQ-manifest contract id/hash lineage
  fields to `StockEtfEvidenceClockDayV1`.
- Added Rust validation blockers for collector/DQ contract-id drift and missing
  lineage hashes.
- Extended the Phase3 evidence TOML template with default-blocked evidence-clock
  lineage fields.
- Exposed fail-closed evidence-clock lineage status through the existing
  `stock_etf.get_evidence_status` fixture, FastAPI normalizer/fallback, and
  display-only GUI evidence panel.
- Added FastAPI contract-violation checks for wrong evidence-clock collector/DQ
  lineage contract ids.

## Boundary

No IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read
probe execution, collector start, market-data ingestion, DQ writer, paper
order/cancel/replace, fill import, DB/evidence/scorecard writer, evidence clock,
tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## Verification

- Python changed files `py_compile`: PASS.
- `node --check` for `tab-stock-etf-evidence-paper.js` and
  `tab-stock-etf-fallbacks.js`: PASS.
- Scoped Rust `rustfmt --edition 2021 --check`: PASS.
- `cargo test -p openclaw_types --test stock_etf_phase3_evidence_acceptance -- --nocapture`:
  `19 passed`.
- `cargo test -p openclaw_types --test stock_etf_phase0_manifest_acceptance -- --nocapture`:
  `6 passed`.
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_evidence_status_routes.py`:
  `4 passed`.

## Dispatch Note

Normal source-contract feature chain is `PM -> PA -> E1/E1a -> E2 -> E4 -> QA
-> PM`. This turn did not spawn sub-agents because the available spawn tool
requires explicit user authorization for delegation; PM performed the narrow
implementation, adversarial review, and focused regression locally.

## PM Sign-Off

APPROVED for source-only checkpoint scope. This is not Phase 3 runtime approval,
evidence-clock approval, collector approval, DQ writer approval, scorecard
writer approval, paper-shadow launch approval, or any IBKR live/tiny-live
authority.
