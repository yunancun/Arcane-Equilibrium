# Operator Brief — AEG-S1 Storage Decision Recorded

Date: 2026-06-01
Source report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-01--aeg_s1_operator_storage_decision.md`

## Recorded Decision

Approved:

1. `market.klines` `1095 days` retention path for OHLCV history, with DB
   provenance ledger.
2. Dedicated research-history storage for funding/OI/long-short.

Not approved yet:

- Migration apply.
- Retention mutation.
- New table/schema apply.
- Bybit historical writer.
- Backfill run.
- Endpoint ingestion.
- Alpha scoring or promotion verdict.

## Work Opened

- Continue `AEG-S1-FND-2` PIT universe builder contract.
- Open `AEG-S1-FND-4` endpoint runner/persistence map in parallel.

Both are docs/design/read-only until separately scoped.

Follow-up checkpoint:
`docs/CCAgentWorkSpace/Operator/2026-06-01--aeg_s1_fnd2_fnd4_parallel_integration.md`
records both docs as complete and lists the next schedule.
