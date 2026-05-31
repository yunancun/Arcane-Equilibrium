# PM Report — AEG-S1-FND-1 Storage Change-Control Integration

Date: 2026-06-01
Role: PM(default)
Scope: integrate MIT/PA read-only sub-agent fanout plus local Linux reflection for `AEG-S1-FND-1`.
Mode: docs/design/read-only; no DB write, migration apply, retention mutation, runtime deploy, auth, order, execution, collector, endpoint ingestion, backfill run, alpha scoring, or promotion verdict.

## Verdict

PM VERDICT: **FND-1 PACKAGE COMPLETE / IMPLEMENTATION STILL BLOCKED**.

The first-priority task is complete as a storage, retention, provenance, and
change-control package:

- Package: `docs/execution_plan/2026-06-01--aeg_s1_fnd1_storage_retention_provenance_change_control.md`
- Recommendation: `market.klines` 1095d for OHLCV after reviewed retention
  mutation and DB provenance ledger; dedicated research-history tables for
  funding/OI/long-short.
- Current runtime truth: Linux still has `market.klines=365d`,
  funding/OI/long-short `=180d`. No 18mo local history is present.

This does not authorize E1 implementation. The DB mutation, Bybit historical
writer, endpoint ingestion, backfill run, and alpha scoring remain blocked.

## Parallel Work Used

| Bound role | Runtime nickname | Task | Result |
|---|---|---|---|
| `MIT(explorer)` | Zeno | Audit schema, retention, writer/provenance surfaces. | Confirmed V002 comments conflict with V006/runtime policy; recommended kline raw-table path only with provenance ledger and dedicated research storage for funding/OI/LS. |
| `PA(explorer)` | Lovelace | Audit change-control, artifact, client, and dispatch constraints. | Confirmed FND-1 must be a decision package; writer/migration remain blocked; provided document structure and gate checklist. |

PM local verification added Linux read-only reflection for actual Timescale jobs,
sizes, row counts, and `_sqlx_migrations` head.

## Key Facts

| Surface | Runtime policy / state | Decision |
|---|---|---|
| `market.klines` | 365d retention, 14d compression, 1.71M rows, 243 MiB, live collector era only. | Candidate OHLCV surface after 1095d change + provenance ledger. |
| `market.funding_rates` | 180d retention, 1,892 rows, 25 symbols, no 2024 rows. | Do not rely on raw extension alone; use dedicated research history unless operator rejects. |
| `market.open_interest` | 180d retention, 158k rows, 25 symbols. | Same dedicated research-history recommendation. |
| `market.long_short_ratio` | 180d retention, 13,473 rows, 25 symbols. | Same dedicated research-history recommendation. |
| `market.market_tickers` | 90d Timescale policy and REF-21 45d prune default; current snapshots only. | Excluded from historical mark/index/basis proof until FND-4. |
| `market.symbol_universe_snapshots` | PIT fields, source URI, payload hash/json, delist flags. | Required PIT universe SSOT for future collection. |

## Still Blocked

- `market.klines` runtime retention mutation.
- Any new research-history schema or DB provenance ledger migration.
- Bybit historical DB writer.
- Funding/OI/long-short 18mo ingestion.
- Mark/index/premium price-kline ingestion.
- Listing collector implementation.
- Alpha scoring, robustness matrix, promotion report, candidate verdict.

## Next Schedule

1. Operator/PM signs the FND-1 decision card.
2. If signed, open a narrow MIT migration-design task for kline retention +
   provenance ledger + funding/OI/long-short research storage.
3. Run E2/E4 migration/change-control review and Linux PG dry-run/double-apply
   before any apply.
4. In parallel, continue docs/design/read-only `AEG-S1-FND-2` PIT universe
   builder and `AEG-S1-FND-4` endpoint runner/persistence-gap map.
5. Only after storage and endpoint design pass, open `S1-W1-S2` historical
   writer implementation.

## PM Sign-Off

PM SIGN-OFF: **CONDITIONAL**.

Condition to unlock implementation: operator chooses the storage branch and the
future V### packet passes MIT/E2/E4/BB gates. Until then, FND-1 is a completed
planning artifact, not an implementation clearance.
