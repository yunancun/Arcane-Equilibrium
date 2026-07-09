# E4 Regression Test Report - ALR P2-2 Persistence

Date: 2026-07-09
Verdict: PASS

| Engine | Result | Baseline | Delta |
|---|---:|---|---|
| P2 focused plus ALR adjacency, run 1 | 160 passed, 0 failed | P2-1 slice 153 passed | +7 |
| P2 focused plus ALR adjacency, run 2 | 160 passed, 0 failed | Run 1 | 0 |
| Python bytecode compilation | PASS | N/A | N/A |
| SQL checksum guard | PASS | Locked V001-V150 unchanged | 0 locked-byte drift |
| Linux disposable PostgreSQL | PASS | N/A | V151 double-apply and repository round trip |

The seven new repository tests cover plan hashing, zero authority, atomic
persistence, duplicate event handling, hash-conflict rollback, mapping-row
drivers, concurrent source-insert race normalization, bounded unseen-source
query, and V151 static append-only ownership. The source migration was applied
twice in a disposable Linux Docker PostgreSQL instance; replays kept ledger
counts stable. A `trading_ai` role could SELECT/INSERT and was denied UPDATE.

A real local `psycopg2` repository round trip reached the isolated database over
an SSH tunnel: `PERSISTED`, `DUPLICATE`, unseen query empty after persist,
restart reconstruction, and changed-hash rollback all passed. The tunnel and
containers were removed. Rust/SLA/cross-language float tests are not applicable
to this Python/SQL persistence slice; no Rust source or numerical calculation
changed. E4 role memory is pre-existing dirty and was not edited.
