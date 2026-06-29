# Operator Summary - IBKR Stock/ETF DB Evidence DDL Contract

Date: 2026-06-30
Status: **DB evidence DDL source contract done; migration/runtime still blocked**

PM added a Rust source contract for `stock_etf_db_evidence_ddl_v1`.

It validates future stock/ETF evidence-schema review for:

- required `broker`, `research`, and `audit` schemas
- required stock/ETF evidence tables
- instrument/order/fill/scorecard natural keys
- `stock_etf_cash` lane checks
- IBKR broker checks
- live environment denial
- paper/shadow table separation
- synthetic shadow fill checks
- raw artifact hash retention
- `audit.asset_lane_events`
- Guard A/B/C migration controls
- future E2/E4 review, Linux PG dry-run, and double-apply requirements

Safety result:

- default contract blocks
- template is secret-free
- source SQL remains outside `sql/migrations/`
- DB apply is rejected
- PG write is rejected
- sqlx migration registration is rejected
- PM/Operator apply authorization claims are rejected
- serialized secret content is rejected

Verified:

- targeted rustfmt: pass
- DB evidence DDL acceptance tests: 7 passed
- full `openclaw_types`: 35 unit/golden + 110 integration passed

Still blocked:

- no immutable Phase 2 PASS artifact
- no real secret/topology evidence
- no IBKR API call or healthcheck
- no secret creation or secret-content read
- no connector
- no paper order
- no migration copy/apply
- no PG write
- no audit writer
- no collector
- no evidence clock
- no GUI lane authority
- no tiny-live/live/margin/short/options/CFD/transfer/account-management/Client Portal path

This is source contract work only. It makes future schema review machine-checkable; it is not migration approval.
