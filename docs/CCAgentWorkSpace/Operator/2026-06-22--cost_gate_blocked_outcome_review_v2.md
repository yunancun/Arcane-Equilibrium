# Cost Gate Blocked Outcome Review v2

這批把「Cost Gate 擋掉的信號是否可能被錯殺」做成更直接的排序面。

變更：

- blocked-outcome review schema 升到 `cost_gate_demo_learning_lane_blocked_outcome_review_v2`
- 每個 side-cell 增加 `wrongful_block_score`、`net_cost_cushion_bps`、review rank、gross/cost 聚合與 horizon 統計
- activation preflight、cron status、alpha-discovery blocker row 會鏡像 top review opportunity

這不會降低 Cost Gate，也不授予 probe/order 權限。它只讓之後如果 runtime learning lane 開始積累 outcome，我們能直接知道哪個被擋信號最值得人工/QC review 後做 bounded demo-probe。

驗證：

- `test_cost_gate_learning_lane_policy.py` + `test_alpha_discovery_throughput.py`：108 passed
- `test_cost_gate_learning_lane_cron_static.py`：12 passed
- focused `py_compile` / `bash -n`：passed

邊界：本輪只改 source/test/docs；沒有 runtime sync、沒有刷新 artifact、沒有裝 cron、沒有啟 writer、沒有寫 PG、沒有連 Bybit、沒有下單、沒有降低 Cost Gate。
