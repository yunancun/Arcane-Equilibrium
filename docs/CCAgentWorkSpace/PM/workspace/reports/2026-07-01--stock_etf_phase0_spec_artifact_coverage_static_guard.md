# 2026-07-01 — Stock/ETF Phase0 Spec Artifact Coverage Static Guard

## Scope

PM added a source-only meta guard for the Stock/ETF/IBKR Phase0 spec artifacts under
`docs/execution_plan/specs`.

This is not a runtime behavior change, not IBKR contact, not connector runtime wiring, not secret
access, not DB migration apply, not paper order routing, and not a Bybit behavior change. It only
locks that the Phase0 manifest, named contract packet, and DB evidence source SQL remain directly
referenced by tests and launch trace documents.

## Guard Added

- `tests/structure/test_stock_etf_phase0_spec_artifact_coverage_static.py`

The guard pins:

- the current Stock/ETF/IBKR spec artifact set is exactly:
  `2026-06-29--stock_etf_cash_phase0_named_contract_packet.manifest.json`,
  `2026-06-29--stock_etf_cash_phase0_named_contract_packet.md`, and
  `2026-06-29--stock_etf_db_evidence_ddl_v1.source_only.sql`;
- unrelated Bybit/runtime spec files are not selected by the Stock/ETF/IBKR scan;
- every selected spec artifact is directly referenced by existing structure, Rust acceptance, or
  Stock/ETF control-api tests outside this guard;
- the main IBKR Stock/ETF execution plan and Operator launch summary both list every selected
  artifact;
- the manifest JSON keeps `stock_etf_cash` / `ibkr` / `paper_shadow_only`, loopback-only IB Gateway
  baseline, paper port 4002, no prior IBKR call, all global denials, and fail-closed phase unlocks;
- the named contract packet keeps the no-runtime-authority denial list;
- the DB evidence SQL remains source-only and is not copied into `sql/migrations`.

## Verification

- New structure guard py_compile: PASS.
- Focused new guard pytest: `6 passed`.
- Focused Phase0/source-static pytest subset: `31 passed`.
- Rust Phase0 manifest acceptance: `6 passed`.
- Rust release packet acceptance: `8 passed`.
- Rust DB evidence DDL acceptance: `10 passed`.
- Docs PM trace tests: PASS.
- Diff check: PASS.

## Boundary

No IBKR SDK import, no socket/HTTP, no secret read or creation, no connector runtime, no read-only
probe, no result import, no evidence or scorecard writer, no DB apply, no paper order route, no
tiny-live/live authorization, and no Bybit live/demo execution change.
