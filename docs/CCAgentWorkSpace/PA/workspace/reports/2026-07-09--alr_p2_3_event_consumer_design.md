# PA Design - ALR P2-3 Event Consumer

Date: 2026-07-09
Verdict: FEASIBLE_WITH_PRESTART_GATES
Risk: High - isolated Rust writer and user-service additions, no trading path.

## Event Path

```text
Rust scanner -> existing TradingMsg::ScannerSnapshot
  -> successful trading.scanner_snapshots batch insert
  -> best-effort pg_notify(alr_scanner_snapshot_v1, identity-only JSON)
  -> Python LISTEN consumer wake
  -> one bounded fetch_unseen_scanner_snapshots drain
  -> P2-1 validation + P2-2 atomic append-only persistence
```

`pg_notify` occurs only after `should_clear_buffer` confirms the snapshot batch
fully succeeded. Notification failure logs a warning but neither retains nor
replays the scanner buffer. The listener treats notification content only as a
wake signal; it re-reads bounded unseen rows from the canonical scanner table.
Therefore a missed notification is repaired by the startup backlog reconciliation
and cannot create a false source record.

## Consumer Contract

- Session-scoped PostgreSQL advisory lock plus `flock` runtime-file lock prevents
  multiple consumers.
- Startup runs one bounded reconciliation; later drains follow only valid LISTEN
  notifications. Timeout wakes only observe SIGTERM and never initiate learning.
- Batch size is clamped; one notification burst is coalesced into one drain.
- Every cycle reuses the P2-1 adapter and P2-2 repository. Invalid notification,
  row, authority, or persistence state fails closed and records no promotion.
- SIGTERM exits after releasing locks and closing the DB connection.

## Service And Identity

The user unit is source-only until prestart review. It has no timer/cron, uses
`Restart=on-failure`, `RuntimeDirectory=alr-shadow`, resource caps, and a
separate DSN-file path. Its future DB login must be a non-superuser, non-owner
role with only CONNECT, schema USAGE, scanner SELECT, and ALR SELECT/INSERT.
It must not reuse `trading_admin`; role/credential creation is a later exact
runtime action.

## E1 Split And E2 Focus

1. E1 adds notification helper/test in `trading_writer.rs`, consumer module and
   tests, and user-unit template/install script with no apply behavior.
2. E2 must verify notification is post-success/warn-only/identity-only, no
   scanner behavior change, LISTEN not polling, locks/releases, batch clamps,
   no direct authority imports, and unit has no timer/enable/start action.
3. E4 runs Python tests twice and relevant Rust tests; isolated PostgreSQL tests
   validate LISTEN wake plus locked duplicate-consumer rejection.

## Rollback

Disable the future user unit and leave the listener unstarted. The writer's
notification can be removed only in a later forward source change; scanner rows
and ALR provenance stay intact. No source design here changes engine or service.

PA DESIGN DONE: docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-09--alr_p2_3_event_consumer_design.md
