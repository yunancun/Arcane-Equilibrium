# MM Low-Friction Signal Scorecard

Date: 2026-06-20

## Summary

This checkpoint turns the MM cost-wall next trigger into an actual read-only search. `fill_sim` now builds placement-time recent-flow and L1-churn features, then runs a train/holdout scorecard to test whether any sample-gated low-friction surface can clear the current 4.0bp maker round trip.

The best new holdout near miss improved the measured gross edge to 2.838bp, but it still does not clear current fees.

## Changes

- Added `add_low_friction_microstructure_features()` to `program_code/research/microstructure/fill_sim.py`.
- Added `fill_sim_low_friction_signal_scorecard()` with train-only thresholds replayed on holdout.
- Included low-friction holdout cells in maker-fee sensitivity and MM gross-edge decomposition.
- Surfaced low-friction status and best holdout candidate through `mm_cost_wall_escape_v1`.
- Fixed alpha runtime ingestion of oversized MM status lines by expanding `_latest_json_line()` tail scanning beyond 256KB.

## Runtime Evidence

Linux read-only artifact loop:

- fill_sim report sha256: `7d152298cee8ac81821afe97bf5e3003ac8ed460bce71cb13499e5d989d07e6c`
- fill_sim generated: `2026-06-20T19:36:53.831449+00:00`
- L1 rows post-filter: `1,004,009`
- Trades rows: `843,279`
- Low-friction candidates evaluated: `96`

Best direct low-friction holdout:

- Rule: `quoted_half_spread_bps train_p90 AND side_touch_size_delta_frac_30s train_p90`
- Gross edge before fees: `2.838bp`
- Net at current fees: `-1.162bp`
- Fill-only n: `81`

Latest alpha:

- sha256: `c87f9d538a1cf5dc7480d8d6f76e2048fe0278042812aa7dc725a9cea6890bba`
- created: `2026-06-20T19:46:40.560943+00:00`
- status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- `engineering_actionable_count`: `1`
- MM best sample-gated gross edge: `2.838bp`
- Required current-fee gross edge: `4.0bp`
- Gap: `1.162bp`
- Multiple to clear current fee: `1.4094`

Polymarket remained near-gate during this run: sample `28/30`, ETA `2026-06-20T19:52:01.636000+00:00`.

## Interpretation

The new recent-flow/L1-churn surface materially improves the near miss versus the prior 2.27bp/2.002bp readings, so the MM family is not useless. But the best holdout cell is still below the current-fee threshold. This narrows the problem: current-fee profitability still needs either materially stronger signal information or an actually accessible lower-fee/rebate path.

## Verification

- Mac: `test_fill_sim_cost_wall.py` = 20 passed.
- Mac: `test_fill_sim_refresh_cron_static.py` = 11 passed.
- Mac: `test_alpha_discovery_throughput.py` = 29 passed.
- Mac: bash syntax, py_compile, and `git diff --check` passed.
- Linux: same focused suites = 20 passed + 11 passed + 29 passed.
- Linux: bash syntax and py_compile passed.
- Linux: read-only fill_sim force refresh, MM verdict, and alpha-discovery smoke refreshed the evidence above.

## Boundary

Source/test/docs plus selective Linux source sync and `/tmp/openclaw` artifact/log writes only. No PG table write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart, no credential/auth/risk/order/strategy mutation.

This is not a trading signal, not candidate promotion proof, and not authority to change live/demo parameters.
