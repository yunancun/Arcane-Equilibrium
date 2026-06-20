# Polymarket Source-Split IC View

v273 upgrades the Polymarket lead-lag lane to v0.10. It does not add a trading signal. It keeps the aggregate `event_reg` view but adds `event_reg_direct` and `event_reg_macro` source-split IC cells, so direct asset events and generic macro/reg proxy rows are tested separately.

Latest Linux v0.10 artifact is still `INSUFFICIENT_SAMPLE`: feature points `208`, joined rows `341`, adjusted sample `13 / 30`, ETA `2026-06-20T19:52:02.188Z`, candidate_count `0`, pre-gate watchlist `0`.

Alpha discovery now passes split counts through detail and keeps `RUN_READ_ONLY_CAPTURE`.

No trading change, no crontab reinstall, no restart. Boundary stayed artifact-only/read-only.
