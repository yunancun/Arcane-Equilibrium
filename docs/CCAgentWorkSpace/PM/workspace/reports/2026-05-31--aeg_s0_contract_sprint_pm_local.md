# PM Report — AEG-S0 Contract Sprint PM-Local Draft

Date: 2026-05-31
Role: PM(default)
Scope: First-priority AEG-S0 contract sprint.
Mode: documentation / governance only. No runtime deploy, DB write, migration,
auth change, secret change, order, collector implementation, backfill, or alpha
scoring.

## Verdict

PM SIGN-OFF: **CONDITIONAL / CONTRACT DRAFT READY FOR FORMAL ROLE REVIEW**.

AEG-S0 now has a concrete contract draft:

- `docs/execution_plan/2026-05-31--aeg_s0_contracts.md`

This is not a PA/MIT/QC/BB/TW/CC independent sign-off. E1 remains blocked until
the formal role review chain approves or amends the contracts.

## What Changed

1. Added one AEG-S0 contract file covering:
   - `AEG-S0-W0-S1` Evidence Storage Contract,
   - `AEG-S0-W0-S2` Regime Classifier Freeze,
   - `AEG-S0-W0-S3` Bybit Endpoint Contract,
   - `AEG-S0-W0-S4` TODO Archive Plan.
2. Updated `TODO.md` so the next action is formal role review, not E1
   implementation.
3. Updated the Alpha-Edge engineering arrangement to point at the new contract
   draft and preserve the role-review boundary.
4. Updated `docs/README.md` index with the AEG-S0 contract and governance
   pointers.

## Key Contract Decisions

- Alpha runs must emit a reconstructable manifest/coverage/universe/regime/
  breadth/execution-realism artifact set keyed by `run_id`.
- `panel.*` 14d surfaces are not valid 18mo alpha-history.
- `market_tickers.index_price` and `market_tickers.mark_price` remain excluded
  from historical basis until the known persistence bug is fixed or bypassed.
- Regime classifier version `aeg_regime_v0.1.0` uses only closed bars and
  requires lagged / shifted features before alpha scoring.
- Bybit endpoints are raw state inputs; endpoint adoption requires BB review,
  fail-closed retCode/timeout behavior, pagination guards, and same-commit
  reference updates when semantics change.
- TODO should keep active next actions and pointers only; large artifacts and
  evidence bodies stay in reports/runtime artifacts/archive.

## Evidence Read

Local source files:

- `TODO.md` v96 as input; output updated to TODO v97 in commit `ca4c569c`
- `docs/adr/0047-alpha-edge-regime-evidence-governance.md`
- `docs/governance_dev/amendments/2026-05-31--AMD-2026-05-31-01-alpha-edge-evidence-governance.md`
- `docs/execution_plan/2026-05-31--alpha_edge_regime_evidence_engineering_arrangement.md`
- `docs/execution_plan/2026-05-31--alpha_edge_research_execution_plan.md`
- `docs/execution_plan/specs/2026-05-31--historical-kline-backfill-spec.md`
- `docs/execution_plan/specs/2026-05-31--collector-listing-capture-spec.md`
- `sql/migrations/V002__market_tables.sql`
- `sql/migrations/V006__timescaledb_policies.sql`
- `sql/migrations/V058__symbol_universe_and_strategy_freeze_log.sql`
- `sql/migrations/V085__panel_funding_curve.sql`
- `sql/migrations/V087__panel_oi_delta_panel.sql`
- `sql/migrations/V115__panel_basis_panel.sql`
- `docs/references/2026-04-04--bybit_api_reference.md`

Official Bybit docs checked on 2026-05-31 for endpoint semantics:

- Kline, funding history, open interest, long/short ratio, mark/index/premium
  kline, tickers, instruments-info, orderbook, historical volatility, and rate
  limit pages.

## Remaining Gates

Required next action:

- Formal role review: PA/MIT/QC/BB/TW/CC review `2026-05-31--aeg_s0_contracts.md`.

Still blocked:

- Bybit historical backfill writer.
- `market.klines` retention/runtime PG mutation.
- funding/OI/long-short 18mo backfill.
- mark/index/premium kline client implementation.
- listing-capture collector implementation.
- alpha scoring / promotion report.

## Open Operator / PM Choices For Later

These are not blockers for the S0 draft but block later implementation:

- `market.klines` retention path: 1095d vs 12mo floor vs dedicated history table.
- funding/OI/long-short 18mo storage path.
- explicit DB provenance ledger vs artifact-only manifest plus timeframe
  namespace.
- Python replay-client implementation path vs Rust runner path.
- whether option historical volatility belongs in the core matrix.

No runtime verification was run because this was a documentation/governance
contract sprint only.
