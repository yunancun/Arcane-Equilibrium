# 2026-06-20 -- fill_sim refresh guard + L1 stale diagnosis

## Summary

We closed a live MM evidence blind spot and found the next upstream blocker.

Changes landed:
- Added `helper_scripts/cron/fill_sim_refresh_cron.sh`.
- Added candidate validation before replacing `/tmp/openclaw/research/fillsim/fillsim_report.json`.
- Added `l1_min_ts/l1_max_ts/l1_max_age_hours` to `fill_sim.py` reports.
- Hardened `recorder_mm_verdict_cron.sh` to reject empty/stale L1 data even when `generated_at` is fresh.
- Installed Linux crons:
  - `5 6 * * * ... fill_sim_refresh_cron.sh`
  - `23 6 * * * ... recorder_health_cron.sh`
  - existing `41 6 * * * ... recorder_mm_verdict_cron.sh`

## Runtime Evidence

Local verification:
- `bash -n helper_scripts/cron/fill_sim_refresh_cron.sh`
- `bash -n helper_scripts/cron/recorder_mm_verdict_cron.sh`
- `python3 -m py_compile program_code/research/microstructure/fill_sim.py`
- `python3 -m pytest -q helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py` = 10 passed
- Fresh-report skip smoke = `skipped_fresh 0 True 1`

Linux verification:
- Same bash/py_compile/pytest checks passed.
- `OPENCLAW_FILL_SIM_FORCE=1 OPENCLAW_FILL_SIM_HOURS=2` correctly rejected the candidate:
  - action `candidate_rejected`
  - reason `abort`
  - candidate `l1_rows_post_filter=0`
- Full `HOURS=0` recovery was terminated after about 30 minutes because it loaded post-L1-stop trades (`59.6M`) and was not a viable routine path.
- Explicit 90m post-fix recovery succeeded:
  - `l1_rows_post_filter=1,750,468`
  - `trades_rows=1,841,649`
  - `n_symbols=37`
  - fill-only `n=15,208`
  - `adverse_sel_bps@15=1.477`
  - `net_bps@15_maker_exit=-4.701`
  - `l1_max_age_hours=58.114`

Manual MM verdict after recovery:
- `adverse_selection_usable=true`
- `markout_n_total=16`, `markout_n_24h=5`
- all net edges still negative
- closest symbols: `ARBUSDT=-0.1437bp`, `NEARUSDT=-0.5815bp`, both far below sample gate

Recorder health:
- `market.trades` stale `0.02min`
- `market.ob_top` stale `0.02min`
- `market.l1_events` max_ts `2026-06-17T21:55:45.438+02:00`
- `market.l1_events` stale `3132.1min`, `rows_24h=0`
- alert appended: `[RECORDER-HEALTH] recorder stalled`

Alpha discovery killboard after recovery:
- active true
- action counts `RUN_READ_ONLY_CAPTURE=2 / WAIT=2 / BLOCK=1`
- MM arm `CAPTURING`, sample `16`
- `ready_for_probe=0`, `ready_for_aeg_chain=0`

## Finding

The MM path was not failing only because the verdict status was stale. The upstream L1 event recorder has stopped while trades and ob_top remain fresh. That makes current-regime fill simulation impossible. Any fill_sim rerun over the recent 2h window produces an empty L1 report.

The new guard prevents an empty candidate from overwriting the production report. The new data-age field prevents a freshly generated report from hiding stale underlying L1 data.

## Boundary

No engine/API deploy, rebuild, or restart.
No PG table writes.
No Bybit private/signed/trading calls.
No credential/auth/risk/order/trading mutation.

Writes were limited to source/test/docs, Linux user crontab, and `/tmp/openclaw` artifact/log/heartbeat/alert files.

## Next

Repair or restart the L1 event recorder path. Without fresh `market.l1_events`, the data-age gate will make adverse selection unavailable again around 72h after the current `l1_max_ts`.
