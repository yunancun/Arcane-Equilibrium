# IBKR Stock/ETF DB Evidence DDL Contract Checkpoint

Date: 2026-06-30
Status: **DONE_WITH_BOUNDARY - source-only DB evidence DDL contract**
Scope: `stock_etf_db_evidence_ddl_v1` for `stock_etf_cash` paper/shadow evidence storage.

## Result

The Phase 0 contract packet now has a machine-checkable Rust source contract for the Stock/ETF DB evidence DDL boundary:

- `openclaw_types::stock_etf_db_evidence_ddl` defines `StockEtfDbEvidenceDdlContractV1`, typed blockers, and verdict output.
- The validator requires the source-only SQL path, required `broker` / `research` / `audit` schemas, all required evidence tables, natural-key declarations, stock/ETF lane checks, IBKR broker checks, live-environment denial, paper/shadow table separation, synthetic shadow checks, raw artifact hash retention, `audit.asset_lane_events`, forward-only evidence retention, and destructive-cleanup rollback denial.
- It requires Guard A/B/C migration controls and future E2/E4 review, Linux PG dry-run, and idempotency double-apply requirements.
- It rejects migration file paths, copied-to-`sql/migrations` claims, DB apply, PG write, sqlx migration registration, PM/Operator apply authorization claims, and serialized secret content.
- `settings/broker/stock_etf_db_evidence_ddl.template.toml` is default BLOCKED and secret-free.
- Acceptance tests also inspect the source-only SQL draft and verify key DDL surfaces remain present without moving it into migrations.

This closes the gap where the DDL draft existed as text but was not yet tied to a reusable source-level contract that future E2/E4/QA/PM review can validate before any migration discussion.

## Dispatch Note

Normal feature flow is `PM -> PA -> E1 -> E2 -> E4 -> QA -> PM`. This checkpoint was handled in the main session because no subagent tool was available in this turn and the change is a narrow source-only contract with no runtime, PG, broker, or secret surface. PM performed triage, implementation, focused adversarial checks, and regression locally; full role signoff is still required before any migration apply or runtime DB work.

## Hard Boundary

This checkpoint does not copy SQL into `sql/migrations/`, open Postgres, run PG dry-run, register sqlx migrations, apply DDL, write PG, inspect secrets, contact IBKR, start collectors, start the evidence clock, or authorize:

- IBKR API call or healthcheck
- IBKR connector implementation
- broker-paper order submission/cancel/replace
- active migration apply
- audit writer/runtime
- GUI lane authority
- tiny-live/live execution
- margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue.

## Verification

- `rustfmt rust/openclaw_types/src/stock_etf_db_evidence_ddl.rs rust/openclaw_types/tests/stock_etf_db_evidence_ddl_acceptance.rs` - pass
- `cargo test -p openclaw_types --test stock_etf_db_evidence_ddl_acceptance` - 7 passed
- `cargo test -p openclaw_types` - 35 unit/golden + 110 integration passed

## Next Gate

First IBKR contact remains blocked by missing real secret/topology evidence and missing immutable Phase 2 PASS artifact. DB migration apply remains separately blocked by E2/E4 review, Linux PG dry-run, idempotency double-apply proof, and explicit PM/Operator migration authorization.
