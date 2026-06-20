# 2026-06-20 FlashDip Touchability Monitor

FlashDip is not currently failing because the intended limit is missing. The latest read-only diagnosis shows the orders are simply too deep to trade in the observed window.

72h read-only result from trade-core isolated smoke:

- 19 orders labeled `flash_dip_buy`
- 18 true FlashDip after joining intents
- 1 mislabeled/misattributed row: POLUSDT intent was `grid_trading`
- 0/18 true FlashDip orders touched their intended limit
- median closest miss was `1595.84bp`

The same monitor now emits a K-ladder counterfactual. Latest isolated smoke:

- K15/K12/K10/K8: `0/18` touched
- K6: `1/18` touched
- K4/K5: `2/18` touched
- K2: `4/18` touched
- K1: `14/18` touched

Interpretation: K15 is too deep for this runtime window; K1 would fill but is likely no longer the same tail-dislocation strategy. K2-K6 are the useful exploration band to keep measuring before proposing a retune.

Implemented and activated a read-only cron source `helper_scripts/cron/flash_dip_touchability_cron.sh`. Linux hourly cron is installed at minute 17, and a manual production run wrote `/tmp/openclaw/logs/flash_dip_touchability.log`.

Alpha discovery was refreshed once and now shows FlashDip `CAPTURING_NO_TOUCH`.

Boundary: selective helper/docs deploy + user crontab + local `/tmp/openclaw` logs only; no engine/API restart, no PG write, no Bybit private/signed/trading call, no auth/risk/order mutation. This is diagnostic evidence, not a promotion signal.
