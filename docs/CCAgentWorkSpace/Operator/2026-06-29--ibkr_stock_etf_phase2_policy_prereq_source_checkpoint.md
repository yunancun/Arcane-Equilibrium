# Operator Summary - IBKR Stock/ETF Phase 2 Policy Prerequisites

Date: 2026-06-29
Status: **policy prerequisite source done; first IBKR contact still blocked**

PM added the source policy contracts required by the Phase 2 external gate:

- redaction policy: raw payload hash + redacted summary hash required; account ids, secrets, paths, cookies, tokens, raw payloads, and stack traces denied from logs/reports
- rate-limit policy: global + per-action buckets, spacing, concurrency cap, budgets, and pacing circuit breaker required
- audit event policy: append-only lane/broker/environment/operation/allowed/denial/hash fields required; raw payload storage denied
- paper attestation policy: external gate, session attestation, Rust lane IPC, scoped auth, Decision Lease, Guardian, hashes, idempotency, lifecycle log, reconciliation, paper-only, and live/margin/short/options/CFD denial required
- Python write guard: Python may read/display/import/call Rust IPC, but broker writes, IBKR order methods, live secret access, and GUI authority override are denied

Verified:

- `openclaw_types` IBKR Phase 2 policy acceptance: 8 passed
- full `openclaw_types` crate: 35 unit/golden tests + 31 integration tests passed
- targeted `rustfmt --check`: pass
- `git diff --check`: pass

Still blocked:

- no immutable Phase 2 PASS artifact yet
- no IBKR API call or healthcheck
- no secret slot
- no connector
- no paper order
- no DB migration apply
- no GUI runtime stock/ETF activation
- no evidence clock
- no live/tiny-live/margin/short/options/CFD/transfer/account-management/Client Portal path

Next step is still the reviewed immutable PASS artifact process. The first IBKR read-only contact is not exempt.
