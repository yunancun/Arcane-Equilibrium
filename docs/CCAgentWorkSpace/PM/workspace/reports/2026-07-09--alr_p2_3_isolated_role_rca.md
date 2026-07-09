# PM RCA - ALR P2-3 Isolated Role Probe

Date: 2026-07-09
State: `ACTIVE_E4_RETRY_SELECT_ONLY_FIX`

## Failure

The disposable PostgreSQL listener reached the first real persistence call and
failed with `permission denied for table alr_source_events`. The test role had
the reviewed SELECT/INSERT privilege set; no production PostgreSQL, role,
credential, service, or engine was touched. The disposable container was
removed by its shell trap.

## Root Cause And Repair

`persist_scanner_cycle()` used `SELECT ... FOR SHARE` for its initial and
post-conflict identity checks. PostgreSQL requires an additional row-lock
privilege for that clause, which conflicts with the approved `alr_shadow`
SELECT/INSERT-only boundary. The repository already normalizes concurrent
writers with `INSERT ... ON CONFLICT ... RETURNING` and hash recheck, so the
row lock supplied no required correctness property. The repair removes both
`FOR SHARE` clauses and adds a regression test forbidding them.

## Next

Run focused/adjacent source tests, commit and align the repair, then rerun the
same isolated PostgreSQL LISTEN/ledger/duplicate-lock probe. Do not broaden the
role contract to UPDATE/DELETE or row-lock authority.
