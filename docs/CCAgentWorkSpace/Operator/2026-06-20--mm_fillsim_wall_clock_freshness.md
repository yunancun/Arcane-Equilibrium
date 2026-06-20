# 2026-06-20 -- MM fill_sim wall-clock freshness gate

## Summary

本輪修掉一個會讓 MM adverse-selection evidence 假新鮮的缺口：`fill_sim_refresh_cron.sh` 和 `recorder_mm_verdict_cron.sh` 原本讀的是報告生成時 frozen 的 `l1_max_age_hours`，只要 `generated_at` 還年輕，就可能在 L1 recorder 停住後繼續相信舊 L1。

現在兩條路徑都用 `l1_max_ts` 對當下 wall clock 重算 L1 data age：
- `fill_sim_refresh_cron.sh` 只有在 report fresh、無 abort、L1 rows 非空、且 `l1_max_ts` 未超過 `OPENCLAW_FILL_SIM_MAX_DATA_AGE_H` 時才 `skipped_fresh`。
- candidate validation 也改用 `l1_max_ts` 重算資料年齡；缺 `l1_max_ts` fail-closed。
- `recorder_mm_verdict_cron.sh` 在 verdict 狀態輸出 `fillsim.data_l1_wall_age_hours`，並用它判斷 `adverse_selection_usable`。

## Runtime Evidence

改動前 runtime 現象：
- 2026-06-20 06:05 UTC natural cron skipped production fill_sim report because report age was 4.05h.
- 該 report 的 L1 source actually stopped at `2026-06-17T13:54:59.997Z`; at 2026-06-20T10:39:46Z wall-clock L1 age was 68.746h.
- Without this fix, the next cron could still skip while true L1 age was already beyond 72h, because the frozen `l1_max_age_hours=58.114` would not age.

Linux selective sync + checks:
- Synced only three files to `trade-core`: `fill_sim_refresh_cron.sh`, `recorder_mm_verdict_cron.sh`, and `test_fill_sim_refresh_cron_static.py`.
- Linux `bash -n` for both cron wrappers passed.
- Linux focused pytest `helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py` passed 11/11.
- Linux temp smoke confirmed fresh-L1 report skips, while fresh-report/stale-L1 does not skip and records `stale_reason=stale_l1_data`.

Manual bounded refresh:
- Ran `OPENCLAW_FILL_SIM_FORCE=1 OPENCLAW_FILL_SIM_HOURS=2` on Linux.
- Production report `/tmp/openclaw/research/fillsim/fillsim_report.json` refreshed successfully:
  - sha256 `7ff1f9cbccfb97f43a0bc1abc70ee7eb8c656ebed7ed7da95f278a00847727a8`
  - `generated_at=2026-06-20T10:45:47.206192+00:00`
  - `l1_rows_post_filter=1,022,579`
  - `trades_rows=724,674`
  - `n_symbols=34`
  - `l1_max_ts=2026-06-20T10:45:40.186000+00:00`
  - `l1_max_age_hours=0.002`
  - fill_only `n=21,103`, adverse@15 `0.948bp`, maker net@15 `-4.086bp`
  - `edge_scorecard=NO_POSITIVE_FILL_ONLY_CELL`
  - `walk_forward_feature_scorecard=NO_WALK_FORWARD_FEATURE_TRAIN_POSITIVE`
  - `maker_fee_sensitivity_scorecard=LOWER_FEE_SAMPLE_GATED_POSITIVE`
- History scorecard is now `HISTORY_INSUFFICIENT_WINDOWS` with `valid_windows=1`.

Manual read-only MM verdict after refresh:
- `adverse_selection_usable=true`
- `fillsim.age_hours=0.12`
- `fillsim.data_l1_wall_age_hours=0.119`
- `history_scorecard.status=HISTORY_INSUFFICIENT_WINDOWS`
- `cost_wall_summary.best_symbol_by_net_edge=ARBUSDT`
- `best_net_edge_bps=+0.3853`, but `best_n_maker_fills=1`, below the 30-fill gate.

Alpha discovery after refresh:
- Latest killboard `created_at_utc=2026-06-20T10:53:04.593936+00:00`
- `source_present_count=5`, `active_arm_count=4`, `ready_for_probe=0`, `ready_for_aeg_chain=0`
- `RUN_READ_ONLY_CAPTURE=3`, `WAIT=1`, `BLOCK=2`
- MM remains `CAPTURING`, `sample_count=16`, `artifacts_ready=false`.
- FlashDip L1 replay remains data-gated: `events_with_l1_in_event_window=0`, `events_missing_l1_in_event_window=6`.

## Read

This is not a promoted edge. It makes the MM evidence chain honest and current:
- Production fill_sim is now fresh-L1 instead of relying on a stale 2026-06-17 L1 window.
- Fresh-L1 MM still fails current-fee maker economics at the fill_sim level.
- The apparent live-markout positive ARBUSDT cell has only one maker fill and remains below sample gate.
- Cross-window MM evidence has started accumulating, but with only one valid window it is insufficient.

## Boundary

No rebuild, no restart, no PG table write or schema migration, no Bybit private/signed/trading call, no credential/auth/risk/order mutation, and no strategy parameter change.

Writes were limited to source/test/docs plus Linux `/tmp/openclaw` local artifacts/logs/history/alpha-discovery files.

## Next

Continue accumulating fresh fill_sim windows. Do not promote MM unless cross-window current-fee or holdout-confirmed positives repeat with sample gates. For non-MM path, FlashDip 240m short-exit remains blocked by missing L1 in candidate event windows.
