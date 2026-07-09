# Batch C Operator Brief

Date: 2026-04-29 CEST

Batch C is fixed in the working tree, not deployed.

Closed findings: `OE-001..005`, `OE-008`, `OE-009`, `DBW-001..005`.

Key operator-impacting changes:

- Websocket private events, order dispatch failures, fills, risk verdicts, and DB writer buffers now preserve trading records more defensively.
- Stop and close-all calls now expose partial failures instead of reporting clean success when cancel/close/verify work is incomplete.
- Dirty Python DB connections are rolled back before pool reuse.
- DB migrations no longer hide the exit-features migration under excluded `V999`.
- Auto-migrate now fails closed when enabled but no DB pool is available, unless explicitly allowed for DB-less mode.

Verification:

- Rust targeted tests: 77 passed total across private WS, pending registration, fill emission, batch insert, and migrations.
- Rust `cargo check` passed with existing warnings.
- Python syntax checks passed.
- Python targeted tests: 14 passed.

No deploy/restart was performed.
