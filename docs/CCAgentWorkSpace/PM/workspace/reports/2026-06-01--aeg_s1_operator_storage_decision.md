# PM Report — AEG-S1 Operator Storage Decision

Date: 2026-06-01
Role: PM(default)
Scope: record operator approval of the FND-1 storage branch and open FND-2/FND-4 docs/design work.
Mode: documentation/governance only; no DB write, migration apply, retention mutation, runtime deploy, auth, order, endpoint ingestion, collector runtime, backfill run, alpha scoring, or promotion verdict.

## Decision Recorded

Operator approved FND-1 recommendation:

1. `market.klines` retention extension to `1095 days` for OHLCV history, paired
   with a DB provenance ledger.
2. Dedicated research-history storage for funding, open interest, and
   long-short history.

This is approval of the design branch, not approval to execute a migration or
writer.

## Work Opened

| ID | State |
|---|---|
| `AEG-S1-FND-2` | Continued as PIT universe builder contract using `market.symbol_universe_snapshots`; docs/design/read-only. |
| `AEG-S1-FND-4` | Opened in parallel as public endpoint runner/client-gap + persistence map; docs/design/read-only. |

Sub-agent fanout:

- Cicero `019e8034-d203-7981-a6ed-f57bc0620638`: `MIT(explorer)` for FND-2
  source/schema/artifact audit; completed read-only.
- Aristotle `019e8034-ed72-77e1-b6d1-0dede37c1e24`: `BB(explorer)` for FND-4
  endpoint/client/persistence audit; completed read-only.

## Boundaries

Still blocked:

- V### migration implementation or apply.
- Timescale retention mutation.
- New research-history schema apply.
- Bybit historical DB writer.
- Any endpoint ingestion/backfill run.
- Listing collector runtime.
- Alpha scoring, robustness matrix, promotion report, candidate verdict.

## Immediate Next

FND-2 and FND-4 docs are complete in the parallel integration checkpoint. Next
safe work is FND-3, S2 Gate-B prep, and MIT migration design for the approved
storage branch; execution remains separately gated.
