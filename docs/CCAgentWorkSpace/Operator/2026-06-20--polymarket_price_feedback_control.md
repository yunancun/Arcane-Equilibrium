# Polymarket Price-Feedback IC Control

v274 adds a diagnostic control to the Polymarket lead-lag lane. It does not add a trading signal.

Latest Linux v0.11 artifact is still `INSUFFICIENT_SAMPLE`: feature points `222`, joined rows `371`, adjusted sample `14 / 30`, ETA `2026-06-20T19:52:01.378Z`, candidate_count `0`.

New diagnostic result: `price_feedback_summary.cells_with_control=32`, `warning_count=22`, `max_abs_past_return_ic=1.0`. The strongest warnings are `price_target` BTC/ETH/XRP 15m/60m cells where Polymarket odds deltas correlate more with the previous price move than with the forward return.

Alpha discovery passes the summary through detail and keeps `RUN_READ_ONLY_CAPTURE`.

No trading change, no crontab reinstall, no restart. Boundary stayed artifact-only/read-only.
