# Polymarket Partial IC Control

v275 adds diagnostic partial/residual IC controls to the Polymarket lead-lag lane. It does not add a trading signal.

Latest Linux v0.12 artifact is still `INSUFFICIENT_SAMPLE`: feature points `236`, joined rows `414`, adjusted sample `15 / 30`, ETA `2026-06-20T19:52:01.632Z`, candidate_count `0`.

New diagnostic result: `price_feedback_warning_count=22`, `partial_control_cells=29`, `raw_to_partial_collapse_count=4`, `max_abs_partial_ic_controlling_trailing_return=0.726`. Example: `price_target|XRPUSDT|15m` raw IC around `0.306` collapses to partial IC around `0.095` after trailing-return control.

Alpha discovery passes the collapse summary through detail and keeps `RUN_READ_ONLY_CAPTURE`.

No trading change, no crontab reinstall, no restart. Boundary stayed artifact-only/read-only.
