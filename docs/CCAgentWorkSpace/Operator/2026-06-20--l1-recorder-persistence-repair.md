# L1 Recorder Restored

Date: 2026-06-20

What happened:

- `market.l1_events` was stale because the engine restarted with `OPENCLAW_RECORD_L1_EVENTS` blank.
- `market.trades` and `market.ob_top` stayed fresh because they use `OPENCLAW_RECORD_TICKS=1`.

Fix applied:

- `restart_all.sh` now persists L1 recorder flags from `basic_system_services.env`.
- trade-core env file now has `OPENCLAW_RECORD_L1_EVENTS=1` and `OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL=50`.
- engine-only `--keep-auth` restart started PID `4155643`.

Verification:

- new PID env contains the L1 flags
- `market.l1_events` fresh again: max ts `2026-06-20 02:19:30+02`
- health cron: `rows_24h=4566`, `stale_min=0.03`, crossed/locked `0.00`

Boundary:

- No rebuild, no API restart, no schema migration.
- No Bybit private/signed/trading call.
- No auth/risk/order/trading mutation.
- This restores the evidence feed; it is not a profitability proof.
