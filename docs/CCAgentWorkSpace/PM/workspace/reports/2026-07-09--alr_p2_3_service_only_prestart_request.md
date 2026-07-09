# PM Request - ALR P2-3 Service-Only Prestart

Date: 2026-07-09
Code head: `2d8430c273231c03e9b6865cb63205fce56c8413`
Three-head state: Mac, `origin/main`, and clean Linux checkout equal this head.

## Fresh Runtime Facts

- Existing PostgreSQL: five V151 `learning.alr_*` tables and one source ledger
  row; `alr_shadow` does not exist.
- No ALR systemd user unit or DSN file exists.
- Existing engine is watchdog-owned and has `OPENCLAW_ALLOW_MAINNET=0`, but it
  also has `OPENCLAW_DEMO_LEARNING_LANE_WRITER=1`,
  `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=1`, and
  `BYBIT_CONNECTOR_WRITE_ENABLED=true`.

## Exact Requested Apply

1. Create only a non-superuser/non-inheriting `alr_shadow` login, apply
   `sql/contracts/alr_shadow_role_contract_v1.sql`, and write its local PG DSN
   as `~/.config/openclaw/alr-shadow.dsn` mode `0600`.
2. Copy the reviewed user-unit template to
   `~/.config/systemd/user/openclaw-alr-shadow.service`, daemon-reload, and
   enable/start only that unit.
3. Permit its one bounded startup reconciliation of existing Rust scanner rows
   into append-only `learning.alr_*` records. It has no exchange, trading,
   proof, serving, or promotion authority.

## Explicit Denials

Do not build/restart the Rust engine or watchdog. Do not change scanner
cadence/score/registry/dispatch, existing engine flags, API/gateway, Bybit,
order/probe/cancel/modify, Decision Lease, Cost Gate, RiskConfig, Guardian,
serving/promotion, `_latest`, retention, or non-ALR data. The Rust notifier is
compiled but dormant until a separately safe no-order engine restart scope is
available.
