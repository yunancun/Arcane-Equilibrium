# Operator Brief — AEG-S1 FND-2/FND-4 Parallel Checkpoint

Date: 2026-06-01
Mode: docs/design/read-only. No DB/runtime/backfill/scoring action was taken.

## What Is Complete

- FND-1 design branch is recorded as approved:
  `market.klines` 1095d + DB provenance ledger for OHLCV, and dedicated
  research-history storage for funding/OI/long-short.
- FND-2 PIT universe builder contract is complete.
- FND-4 public endpoint runner/client-gap + persistence map is complete.

## Current Decisions

- PIT universe must come from `market.symbol_universe_snapshots`; the 797-row
  CSV is only seed/regression evidence.
- Current-survivor-only universe fails automatically.
- Historical basis/index should bypass `market.market_tickers`; use price-only
  kline endpoints with a separate storage decision.
- `market_tickers` can be fixed later for forward capture, but cannot prove 18mo
  historical mark/index/funding history.

## Still Not Authorized

- Migration apply or retention mutation.
- DB provenance ledger or research-history table creation.
- Bybit historical writer.
- Endpoint ingestion/backfill.
- Collector runtime.
- Alpha scoring/promotion verdict.

## Recommended Next Work

1. FND-3 side-evidence artifact contract.
2. S2 Gate-B PreLaunch probe plan.
3. MIT migration-design packet for the approved storage branch, still as
   design/review until explicit execution approval.
