# PA Design - ALR P2-2 Append-Only Persistence

Date: 2026-07-09
Verdict: FEASIBLE_WITH_PREAPPLY_GATE
Risk: Medium - new isolated database contract; no scanner/Rust/API/authority mutation.

## Interface

E1 adds `program_code/ml_training/alr_persistence_repository.py` with injected
DB connections and fixed, parameterized SQL only:

- `fetch_unseen_scanner_snapshots(connection, limit)` reads existing
  `trading.scanner_snapshots` through a `NOT EXISTS` ALR ledger join. It never
  writes the scanner table and returns no trading authority.
- `persist_scanner_cycle(connection, cycle)` consumes a P2-1 validated cycle
  in one transaction. A matching source key/hash returns `DUPLICATE`; a matching
  source key with a different hash raises `AlrPersistenceConflict` and rolls
  back; a new cycle persists its raw canonical source artifact, source event,
  immutable ingest event, watermark event, and graph edge atomically.
- `load_restart_state(connection)` reconstructs processed source keys and the
  latest monotonic watermark from the append-only ledger. A crash before commit
  leaves no partial cycle; a crash after commit is recognized as already
  persisted.

`V151__alr_persistence_foundation.sql` creates only these plain tables under
`learning`: `alr_artifact_nodes`, `alr_source_events`, `alr_ingest_events`,
`alr_watermark_events`, and `alr_provenance_edges`. No Timescale dependency is
needed. Each table receives `PUBLIC` and `trading_ai` `UPDATE/DELETE` revokes;
application grants are `SELECT/INSERT` plus necessary sequence usage only.

## Data Flow

```text
trading.scanner_snapshots (Rust-owned, read-only)
  -> fetch_unseen_scanner_snapshots
  -> adapt_scanner_snapshot (P2-1 validation/hash)
  -> atomic persist_scanner_cycle
     -> alr_artifact_nodes (raw scanner and ingest-event artifacts)
     -> alr_source_events (source identity)
     -> alr_ingest_events / alr_watermark_events
     -> alr_provenance_edges (source -> ingest event)
  -> load_restart_state
```

The provenance graph is an ALR-local audit graph. It does not make scanner facts
proof, trading, serving, or promotion authority.

## Failure And Rollback

- Any malformed P2-1 cycle, unknown authority truth, source hash mismatch, or
  SQL failure rolls back the current transaction and raises fail-closed.
- A same-key/different-hash row is an integrity conflict, not a duplicate and
  cannot be overwritten.
- Rollback disables future readers/writers in a later scope; it never deletes
  or alters ALR provenance. P2-6 owns only derived-cache retention, not these
  ledgers.
- Existing-PG apply remains blocked until post-implementation three-head
  alignment and clean Linux recheck. The isolated Docker database is disposable.

## E1 Split And Review Focus

1. E1 writes V151, repository, and behavior/integration tests.
2. E2 must verify atomic conflict rollback, no dynamic SQL identifiers,
   late-cycle watermark non-rewind, and no scanner-table mutation.
3. E4 runs source tests twice plus the isolated Docker double-apply. QA accepts
   only P2-2 persistence, leaving service/training/retention/soak rows open.

Expected footprint: one SQL migration, one Python repository, and one focused
test module. Existing ALR modules remain unchanged.

PA DESIGN DONE: docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-09--alr_p2_2_append_only_persistence_design.md
