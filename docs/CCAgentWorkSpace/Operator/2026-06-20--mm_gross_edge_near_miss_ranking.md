# 2026-06-20 -- MM Gross-Edge Near-Miss Ranking

PM source report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-20--mm_gross_edge_near_miss_ranking.md`.

Runtime read: MM verdict `ts_utc=2026-06-20T19:18:50Z`; alpha latest sha256 `4dbbb4e964b1077f2b901a7d651b06c59d4cc3622c49b132e47b6b4f511c9583`, created `2026-06-20T19:19:00.916678+00:00`.

Operator meaning: MM cost-wall blocker now includes a ranked near-miss list. Best current measured pockets are `LABUSDT` fill-only gross 2.27bp, `ADAUSDT` walk-forward holdout gross 2.002bp, and quoted-half-spread train_p90 holdout gross 1.565bp, all below the 4.0bp current-fee gross-edge threshold. This supports searching for a materially stronger/low-friction signal source rather than continuing same-family threshold tweaks.

Boundary: source/test/docs plus read-only artifact refresh only. No engine/API restart, no rebuild, no strategy parameter change, no order/auth/risk/runtime mutation, and no Bybit private/signed/trading call.
