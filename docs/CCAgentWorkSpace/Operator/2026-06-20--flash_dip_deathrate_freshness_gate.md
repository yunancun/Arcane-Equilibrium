# 2026-06-20 FlashDip Death-Rate Freshness Gate

Alpha discovery now treats stale `flash_dip_death_rate.log` as `SOURCE_FAILURE/stale_artifact`.

Why it matters: FlashDip is the current non-MM strategy line with prior positive research evidence. If its survival monitor cron stops, the killboard must not continue reporting active capture from an old status line.

No trading path, auth, risk, runtime restart, or PG write was changed.
