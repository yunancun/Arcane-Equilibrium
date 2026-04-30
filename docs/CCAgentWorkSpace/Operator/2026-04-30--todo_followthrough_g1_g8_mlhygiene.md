# TODO Follow-through: G1-04 / G8-01 / ML Hygiene

Date: 2026-04-30
Owner: PM

Completed the four requested follow-through items.

Key results:

- Docs/runtime drift corrected to code-bearing runtime checkpoint `a9fce24`; Linux engine stayed alive, no rebuild/restart.
- G1-04 as-of compute: full 5.94d post-G7-09 window still diluted (fee_drop 21.30%), but post-2026-04-29 12:27 reload slice is near target: n=665, maker_like 73.23%, fee_drop 59.32%.
- R:R remains mixed: post-reload grid_close_short net +2.96 / RR 1.454; ma_reverse_cross remains net -4.79 / RR 1.076.
- G8-01 tests verified: 40 passed; `CognitiveModulator` stdlib trace/AST coverage 76/81 (93.8%).
- ML training hygiene: dust spiral noise 37/1843 = 2.01%, 24h recurrence 0; no DB backfill needed. Existing `[26]` and `[21]` healthchecks cover recurrence.

No live authorization, risk parameter, strategy parameter, rebuild, or restart action was performed.
