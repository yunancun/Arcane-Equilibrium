# Operator Brief — TODO v174 Market Tickers Forward-Column SQL Closure

PM removed `P3-MARKET-TICKERS-INDEX-MARK-DEAD-PERSISTENCE` from `TODO.md` §5.

Reason: post-engine-start runtime SQL confirms `market.market_tickers` now receives non-NULL mark/index/OI/funding forward fields. Since current engine PID 3134818 started at `2026-06-18 14:11:50+02`, rows after that time show mark_n=40912, index_n=84919, oi_n=5913, funding_n=719.

Mark/index/OI zero counts are 0. Funding has 8 zero rows, which is legitimate zero funding and not missing-data padding.

Boundary: read-only SQL/source check plus docs hygiene only. No deploy, rebuild, restart, DB write, auth/risk/order/trading mutation. No history backfill or retention change.
