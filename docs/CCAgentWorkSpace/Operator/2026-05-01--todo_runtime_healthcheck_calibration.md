# TODO runtime healthcheck calibration

Date: 2026-05-01
Status: Complete

## Result

- `[27] intents_counter_freeze` was checked and is currently PASS. The 18:00 CEST FAIL was transient; manual wrapper reruns at 21:29/21:32 CEST showed recent demo/live_demo intents.
- `[11] counterfactual_clean_window_growth` was a false-red from a rolling `--days 2` replay window. Commit `2674e14` changes rolling-window shrink to WARN while keeping stale JSON and non-rolling regressions as FAIL.
- `TODO.md` and `CLAUDE.md` now reflect the 2026-05-01 scanner/healthcheck state, including `[41] scanner_market_gate_confirmation`.

## Verification

- Counterfactual [11] unit tests: 2/0.
- F7 healthcheck tests: 39/0.
- Linux post-fix healthcheck wrapper: SUMMARY WARN exit 0.
- Watchdog: `engine_alive=true`.

## Boundary

No trading, risk, strategy parameter, live authorization, DB write, rebuild, or restart was performed.
