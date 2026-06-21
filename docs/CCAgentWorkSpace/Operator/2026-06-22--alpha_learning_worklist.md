# 2026-06-22 -- Alpha learning worklist operator note

本輪新增的是 source-side artifact 能力：`alpha_discovery` 現在不只輸出 blocker scorecard，還會輸出 `learning_worklist`。

重點：

- 它把「為何沒盈利」轉成「下一個學習任務是什麼」。
- 它會標記任務是否需要 operator authorization 或 runtime mutation。
- 它不授權下單、不啟動 probe、不降低 Cost Gate、不改 runtime。

對當前 demo/cost-gate 狀態的含義：

- 若 runtime 仍是 behind/dirty 且 learning lane 未啟動，top task 會是 `runtime_source_reconcile`。
- 這會把下一步清楚標成 operator-gated：先 review/preserve/discard runtime dirty paths，再同步 source，之後才談 learning lane activation。
- MM / Polymarket 等其他 arm 則會被排成 read-only engineering learning tasks，例如尋找 train-confirmed 低摩擦 signal 或補 dated replay/execution evidence。

驗證：

- 新增 worklist focused tests `2 passed`
- 既有 alpha discovery focused suite `44 passed`

邊界：本輪無 runtime 寫入、無部署、無重啟、無 PG write、無 Bybit private/signed/trading call、無 Cost Gate lowering。

