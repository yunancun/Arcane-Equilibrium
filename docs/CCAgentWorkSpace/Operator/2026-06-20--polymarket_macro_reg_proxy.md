# Polymarket Macro-Reg Proxy

v272 upgrades the Polymarket lead-lag lane to v0.9. It does not add a trading signal. It improves evidence extraction by mapping generic macro/regulatory `event_reg` markets with no direct asset mention onto BTC/ETH proxy features, while direct BTC/ETH/SOL/XRP asset mapping still wins.

Why this path: a same-data alt-alias probe found `alias_clue_counts=[]`, so adding more random symbols would not have helped. The discarded rows were mostly generic CPI/inflation/Tether/Coinbase SEC/ETF/Fed/regulation markets.

Same-snapshot effect: delta rows increased `6184 -> 13380`, unmapped rows fell `5406 -> 1528`, but feature/joined/sample counts stayed `130/210/12`. Latest Linux v0.9 artifact is still `INSUFFICIENT_SAMPLE`: adjusted sample `12 / 30`, ETA `2026-06-20T19:52:03.743Z`, candidate_count `0`, pre-gate watchlist `0`.

No trading change, no crontab reinstall, no restart. Boundary stayed artifact-only/read-only.
