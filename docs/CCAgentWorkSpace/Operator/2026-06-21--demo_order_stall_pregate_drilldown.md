# 2026-06-21 -- Demo Order-Stall Pre-Gate Drilldown

本輪把 `demo_order_stall_audit.py` 再往前拆一層。

新增結果：audit 現在會列出哪些 `strategy / symbol / decision_type` 有 context rows，但沒有 downstream evaluation / risk / intent / order / fill。

2026-06-21 16:49 +02:00 read-only 實查：

- 最近 4h top context rows 全部是 `signal_generated`。
- top rows downstream join 全部為 0。
- 集中在 `demo / ma_crossover` 多個 symbol：
  - `REUSDT`：549 context rows
  - `LABUSDT`：546
  - `ADAUSDT`：513
  - `NEARUSDT`：494
  - `FILUSDT`：490

這說明短期問題不是 context writer 死掉，而是 `ma_crossover` 的 signal/context stream 沒進 candidate evaluation / Guardian risk。

驗證：

- `python3 -m pytest helper_scripts/db/audit/test_demo_order_stall_audit.py -q` -> `9 passed`
- `py_compile` passed
- remote read-only PG drilldown passed

邊界：只讀 PG + source/test/docs；沒有 deploy/restart、沒有 PG write、沒有 Bybit private/signed/trading call、沒有下單、沒有降低 Cost Gate。
