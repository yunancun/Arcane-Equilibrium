# E2 Review - ALR P2-2 Persistence

Verdict: PASS_TO_E4

The implementation is limited to V151, an injected-connection repository, and
its focused tests. It does not change Rust scanner cadence, score, registry,
dispatch, trading authority, broker clients, API routes, Decision Lease, Cost
Gate, serving, promotion, or retention apply.

One RealDictCursor integration defect was found during the disposable PostgreSQL
run: tuple-only row access broke duplicate/restart paths. E1 added mapping/tuple
row support and a regression test. E2 then found a concurrent source insert
race: a second worker could pass the first lookup and hit the unique constraint.
E1 changed the insert to `ON CONFLICT ... RETURNING`, rechecks the stored hash,
and records `DUPLICATE` on a matching race while conflicting content rolls back.

Review focus passed:

1. Source values are SQL parameters; all table identifiers are constants.
2. The cycle transaction creates source/ingest/watermark/provenance records
   atomically or rolls back; all lifecycle corrections are append-only events.
3. V151 creates only `learning.alr_*` objects, guards its contracts, and grants
   `trading_ai` SELECT/INSERT with UPDATE/DELETE revoked.

E2 role memory is pre-existing dirty and was not edited.
