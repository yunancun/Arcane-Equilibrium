# 2026-06-20 FlashDip Touchability Monitor

FlashDip is not currently failing because the intended limit is missing. The latest read-only diagnosis shows the orders are simply too deep to trade in the observed window.

72h read-only result from trade-core isolated smoke:

- 19 orders labeled `flash_dip_buy`
- 18 true FlashDip after joining intents
- 1 mislabeled/misattributed row: POLUSDT intent was `grid_trading`
- 0/18 true FlashDip orders touched their intended limit
- median closest miss was `1595.84bp`

Implemented a read-only cron source `helper_scripts/cron/flash_dip_touchability_cron.sh` and wired alpha discovery runtime detail so FlashDip can show `CAPTURING_NO_TOUCH` when death-rate remains zero because no order touched.

Boundary: no deploy/restart in this source checkpoint, no PG write, no Bybit private/signed/trading call, no auth/risk/order mutation. This is diagnostic evidence, not a promotion signal.
