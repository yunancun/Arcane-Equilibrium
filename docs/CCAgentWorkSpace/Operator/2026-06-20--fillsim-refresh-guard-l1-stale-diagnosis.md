# 2026-06-20 -- fill_sim refresh guard + L1 stale diagnosis

PM added a safe fill_sim refresh cron and found the upstream blocker.

Installed crons:
- `5 6 * * * ... fill_sim_refresh_cron.sh`
- `23 6 * * * ... recorder_health_cron.sh`
- existing `41 6 * * * ... recorder_mm_verdict_cron.sh`

Key runtime facts:
- Recent 2h fill_sim refresh produced empty L1 and is now rejected instead of overwriting production.
- 90m recovery restored report: `l1_rows_post_filter=1,750,468`, fill-only `n=15,208`, adverse@15 `1.477bp`.
- MM verdict: sample=16, all net edges still negative; no probe/promotion.
- `market.l1_events` stopped at `2026-06-17 21:55:45+02`; stale `3132min`, `rows_24h=0`.
- `market.trades` and `market.ob_top` are fresh.

Next operator-relevant action: repair/restart the L1 event recorder. Without it, MM adverse-selection data will go unavailable again when L1 data age crosses 72h.
