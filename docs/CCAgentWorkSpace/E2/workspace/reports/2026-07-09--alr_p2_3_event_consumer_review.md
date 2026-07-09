# E2 Review - ALR P2-3 Event Consumer

Date: 2026-07-09
Verdict: PASS_TO_ISOLATED_E4
Mode: ROLE_FALLBACK_SINGLE_SESSION

## Findings And Fix

The initial listener sketch used a psycopg2 autocommit connection. That would
make the P2-2 repository's commit/rollback contract ineffective. The source
now performs `LISTEN` followed by an explicit commit, retains normal
transactions for all repository calls, and commits every bounded drain,
including the no-row read case, before returning to `select()`. Errors roll
back and stop the consumer.

## Scope Review

1. Rust calls `pg_notify` only after the scanner batch has fully succeeded.
   Its exact JSON contains only schema version, scan ID, and timestamp; notify
   failure is warning-only and never retains/replays the Rust buffer.
2. Python treats notifications only as wake hints and re-reads bounded unseen
   scanner rows through the P2-1 adapter and P2-2 append-only repository. A
   startup reconciliation is bounded; idle timeouts never drain work.
3. Both a nonblocking runtime-file lock and a session advisory lock are
   required. Busy locks fail closed; SIGTERM/SIGINT releases the advisory lock
   and closes the connection.
4. The user-unit source has no credential, timer, install, enable, or start
   action. Its DSN must be a private regular file explicitly bound to local
   `127.0.0.1:5432`, `trading_ai`, and `alr_shadow`.
5. The role contract creates no login or credential. It reduces an existing
   `alr_shadow` login to non-superuser/non-inheriting, scanner SELECT plus ALR
   SELECT/INSERT; UPDATE/DELETE and all trading/proof/serving/promotion scope
   remain absent.

## Evidence

- Python focused P2-1/P2-2/P2-3 suite: `31 passed`.
- Python bytecode compilation: PASS.
- Rust `database::trading_writer::tests::alr_scanner_notification_is_identity_only`:
  `1 passed`, with `4405` unrelated tests filtered.
- `rustfmt --edition 2021` and `git diff --check`: PASS.

Next: Linux disposable PostgreSQL must validate a least-privilege listener,
actual LISTEN wake, one append-only persistence cycle, duplicate suppression,
and a rejected competing advisory lock. This review does not authorize role
creation, credential writing, engine rebuild/restart, or service start.
