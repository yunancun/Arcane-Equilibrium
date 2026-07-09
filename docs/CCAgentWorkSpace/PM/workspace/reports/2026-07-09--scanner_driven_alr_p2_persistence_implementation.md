# ALR P2-2 Append-Only Persistence

Date: 2026-07-09
Work item: `P2-2-ALR-APPEND-ONLY-PERSISTENCE`
Status: `READY_FOR_PREAPPLY_ALIGNMENT`
Execution mode: `ROLE_FALLBACK_SINGLE_SESSION`

## Result

V151 adds five ALR-owned append-only tables for source artifacts, scanner source
identity, ingest events, watermark history, and provenance edges. The repository
reads only unseen scanner rows, persists a new cycle atomically, emits an
immutable duplicate event, rejects same-key/different-hash content, and rebuilds
restart state from ledger rows.

E2 corrected mapping-row support and a concurrent source-insert race. E4 passed
the seven-suite focused/adjacent set twice at `160 passed`. Linux disposable
PostgreSQL passed migration double-apply, privilege denial, and a real
`psycopg2` repository round trip. All test containers and SSH tunnels were
removed.

## Boundary

The existing Linux PostgreSQL database and scanner rows have not been touched.
No service, exchange, order, Decision Lease, Cost Gate, proof, serving,
promotion, retention sweep, or `_latest` action occurred.

## Next State

Commit/push the exact P2-2 source scope, source-sync Linux with no restart,
prove Mac/GitHub/Linux heads and Linux cleanliness, then run only V151 dry-run,
apply, and ALR-owned postapply verification.
