# Operator Brief — AEG-S1-FND-1 Storage Change-Control

Date: 2026-06-01
Source report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-01--aeg_s1_fnd1_storage_change_control_integration.md`
Mode: docs/design/read-only; no DB write, migration apply, retention mutation, runtime deploy, auth, order, execution, collector, endpoint ingestion, backfill run, alpha scoring, or promotion verdict.

## Decision Needed

FND-1 is complete as a decision package. Implementation remains blocked until
you choose the storage branch.

Recommended branch:

1. Approve `market.klines` retention extension to `1095 days` for OHLCV history,
   but only with a reviewed retention migration and DB provenance ledger.
2. Approve dedicated research-history tables for funding, open interest, and
   long-short history. Do not simply extend raw 180d tables and call the result
   promotion-grade.
3. Keep first collection scope as full 18mo survivorship-corrected collection,
   with core25 as the first primary analysis cohort.
4. Keep the Bybit historical writer locked until the storage migration/rollback
   packet and endpoint runner design pass review.

## Runtime Baseline

Read-only Linux reflection at `2026-06-01 00:36 CEST`:

| Surface | Current state |
|---|---|
| `market.klines` | 365d retention, 14d compression, 1.71M rows, 243 MiB, no 18mo local history. |
| `market.funding_rates` | 180d retention, 1,892 rows, no 2024 rows. |
| `market.open_interest` | 180d retention, 158k rows. |
| `market.long_short_ratio` | 180d retention, 13,473 rows. |
| `market.market_tickers` | current-snapshot/local-recorder surface only; not historical mark/index proof. |

## Still Blocked

- Timescale retention mutation.
- New research-history schema or provenance ledger.
- Bybit historical DB writer.
- 18mo backfill.
- Endpoint ingestion for funding/OI/long-short and mark/index/premium klines.
- Alpha scoring / promotion verdict.

## Next Step

Answer the FND-1 storage decision card. After that, PM can open a narrow
MIT/E2/E4 migration-design and Linux dry-run task.
