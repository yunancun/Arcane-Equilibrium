# Polymarket Query-Set V2 Runtime Activation

2026-06-20 · Operator note

Linux `trade-core` Polymarket artifact collector is now running query-set v2 for both daily and hourly cron.

Active crontab:

```text
41 4 * * * ... OPENCLAW_POLYMARKET_QUERY_SET=v2 ... polymarket_axis_cron.sh daily
7 * * * * ... OPENCLAW_POLYMARKET_QUERY_SET=v2 ... polymarket_axis_cron.sh hourly-topn
```

Backup before reinstall:

```text
/tmp/openclaw/cron_backups/crontab_before_polymarket_query_set_v2_20260620T113342Z.txt
```

Manual smoke artifact:

```text
/tmp/openclaw/polymarket_axis_runs/hourly-topn-20260620T113312Z
query_set_version=v2
http_requests=30
unique_events=107
snapshot_rows=860
errors=[]
```

Boundary: artifact-only public Polymarket API collection; no secrets, no PG, no engine restart, no Bybit private/signed/trading call, no strategy/risk/order mutation.

Rollback: run `OPENCLAW_POLYMARKET_CRON_APPLY=1 helper_scripts/cron/install_polymarket_axis_cron.sh --remove`, then reinstall without `OPENCLAW_POLYMARKET_QUERY_SET` or restore the backup crontab.
