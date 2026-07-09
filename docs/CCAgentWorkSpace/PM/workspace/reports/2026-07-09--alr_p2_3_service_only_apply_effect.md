# PM Apply Effect - ALR P2-3 Service Only

Date: 2026-07-09
State: `P2_3_SERVICE_RUNNING_ENGINE_NOTIFIER_DORMANT`
Authority chain: PM -> E3 -> BB -> PM, `ROLE_FALLBACK_SINGLE_SESSION`

## Applied

- Created `alr_shadow` as non-superuser, no-inherit, connection limit 2.
- Applied the reviewed SELECT/INSERT-only role contract and wrote a local DSN
  as a `0600` file owned by the user.
- Installed/enabled/started `openclaw-alr-shadow.service`; its command contains
  no credential and it is active under systemd user scope.

## Bounded Ledger Effect

Before service start: scanner/source/ingest/watermark/edge =
`79713/1/2/1/1`.

First startup reconciliation: scanner source remained `79713`; ALR
source/ingest/watermark/edge became `33/34/33/33`.

One user-service restart recovery check: scanner reached `79714` from the
already-running Rust engine; ALR source/ingest/watermark/edge became
`65/66/65/65`, with `source_duplicate_keys=0`. The terminating service emitted
false exchange/trading/proof/serving/promotion authority counters.

## Boundary And Next

The existing engine PID remained `1561777`; no engine build/restart or scanner
mutation occurred. Rust post-persist notification source remains dormant because
current engine flags enable demo writer/bounded-probe/connector-write surfaces.
P2-4 may use the durable 64-cycle newly persisted backlog. P2-8 cannot claim
notification-driven new-cycle soak until a separately safe no-order engine
activation path exists.
