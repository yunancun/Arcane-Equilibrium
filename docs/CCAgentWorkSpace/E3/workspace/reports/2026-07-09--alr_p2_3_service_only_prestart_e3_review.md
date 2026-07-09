# E3 Prestart Review - ALR P2-3 Service Only

Date: 2026-07-09
Verdict: `APPROVE_SERVICE_ONLY_ENGINE_RESTART_DENIED`
Mode: `ROLE_FALLBACK_SINGLE_SESSION`

The three source heads are aligned at `2d8430c273231c03e9b6865cb63205fce56c8413`.
The role is absent, V151 ALR tables already exist, and the reviewed listener
has passing isolated PostgreSQL evidence. The unit reads only a private local
DSN and is constrained to scanner SELECT plus ALR SELECT/INSERT.

The requested service-only apply is approved under these conditions:

1. Create no credential in source, shell argv, environment, log, or report;
   use a generated private DSN file mode `0600` and verify its owner/mode.
2. Execute the immutable role contract after creating the role; verify
   `NOSUPERUSER`, `NOINHERIT`, connection limit, scanner SELECT, ALR
   SELECT/INSERT, and denied UPDATE/DELETE.
3. Verify the exact unit hash/template, daemon-reload, and start only
   `openclaw-alr-shadow.service`. Its startup reconciliation is max 32 rows;
   no timer/polling loop may create work without a notification.
4. Before/after evidence must include scanner source count unchanged, ALR
   append-only count delta, active unit state, and false authority counters.

Engine build/restart is denied. Current engine flags enable demo learning lane
writer, bounded probe adapter, and Bybit connector write. Restarting it would
not meet the user hard no-order/no-lease boundary, regardless of mainnet=0.
