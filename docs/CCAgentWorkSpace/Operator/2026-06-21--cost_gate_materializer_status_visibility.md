# 2026-06-21 -- Cost-Gate Materializer Status Visibility

本批補上 v339 後的關鍵可觀測性缺口：系統現在能直接看見 reject materializer 是否啟用、是否跑過、materialized 多少拒單 rows、append 多少 rows、decision counts 是什麼，並把這些欄位帶到 activation preflight 和 alpha-discovery killboard。

Runtime read-only smoke 重新驗證：目前 PG 近 4h 有 20 條 `BTCUSDT` demo Cost Gate reject rows，可在本機內存 materialize 成 20 條 fail-closed ledger rows，並產生 20 條 blocked-signal outcomes。Review 結果是 `NO_DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE`；top side-cell `ma_crossover|BTCUSDT|Buy` 為 `KEEP_COST_GATE_BLOCKED`，avg net 約 `-0.1183bp`，positive pct `0.0`。

解讀：這證明學習鏈路可用，但當前樣本不支持盲目 lower Cost Gate。下一步仍需你授權 runtime source sync / cron activation / append enablement，讓 demo 被擋信號持續積累，之後只對 outcome review 正向的 side-cell 做 demo probe authority review。

邊界：本批只有 source/test/docs + read-only runtime PG/artifact smoke；沒有 runtime sync、沒有 cron install、沒有 ledger append、沒有 PG write、沒有 Bybit private/signed/trading call、沒有下單、沒有啟 writer、沒有降低 Cost Gate。
