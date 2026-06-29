# IBKR Stock/ETF Scorecard Input Contracts Checkpoint

Date: 2026-06-29
Status: **DONE_WITH_BOUNDARY - source-only scorecard input contracts**
Scope: `stock_etf_cash` paper/shadow scorecard atomic input validation.

## Result

Phase 3 now has machine-checkable source contracts for scorecard inputs that were previously mostly prose:

- `BrokerAccountPortfolioCashLedgerV1` validates paper/read-only IBKR cash/account snapshot evidence without allowing live account proof.
- `StockEtfCostModelVersionV1` validates commission, exchange/regulatory fee, spread, slippage, FX drag, tax/fee placeholder, version hash, and conservative fill penalty inputs.
- `StockEtfBenchmarkVersionV1` validates benchmark source, construction, rebalance, currency, corporate-action, matched-control, and version hashes.
- `StockShadowFillModelV1` validates shadow fill reconstruction with `synthetic_shadow=true`, conservative fill or rejection evidence, and no broker-paper/live fill linkage.
- `StockEtfStorageCapacityV1` validates universe/row/retention/index/query/archive capacity inputs and requires capacity breach to block the evidence clock.
- `StockEtfScorecardInputBundleV1` validates the combined atomic input bundle, requires derived-only scorecard status, requires paper/shadow fill separation, and rejects live fill claims.
- `settings/broker/stock_etf_scorecard_inputs.template.toml` is default BLOCKED and secret-free.

This checkpoint keeps daily scorecards as derived artifacts. Atomic facts and hashes remain the evidence source of truth.

## Hard Boundary

This checkpoint does not import broker fills, generate scorecards, apply DB migrations, write PG, read or create secret slots, inspect secret contents, start IB Gateway/TWS, open sockets, start collectors, start the evidence clock, or authorize:

- IBKR API call or healthcheck
- IBKR connector implementation
- broker-paper order submission/cancel/replace
- active DB migration apply
- GUI lane authority
- tiny-live/live execution
- margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit remains the only active live execution venue.

## Verification

- `rustfmt rust/openclaw_types/src/stock_etf_scorecard_inputs.rs rust/openclaw_types/tests/stock_etf_scorecard_inputs_acceptance.rs` - pass
- `cargo test -p openclaw_types --test stock_etf_scorecard_inputs_acceptance` - 7 passed

## Next Gate

First IBKR contact remains blocked by missing real secret/topology evidence and missing immutable Phase 2 PASS artifact. Scorecard input contracts are source-only until real collector, DQ, archive, and scorecard regeneration evidence exists behind the required Phase 2/3 gates.
