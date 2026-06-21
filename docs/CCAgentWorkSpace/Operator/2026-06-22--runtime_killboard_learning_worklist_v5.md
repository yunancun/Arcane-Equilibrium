# 2026-06-22 -- Runtime killboard learning worklist v5

本輪把 `alpha_discovery_runtime_killboard` 升到 v5。

新增的價值是：runtime alpha artifact 的頂層 `killboard` 現在會直接顯示 learning worklist 狀態與 top learning task，例如：

- `learning_worklist_status`
- `learning_task_count`
- `learning_operator_required_count`
- `learning_runtime_mutation_required_count`
- `top_learning_task_type`
- `top_learning_task_arm_id`
- `top_learning_task_actionability`

這讓 operator 不用深入解析完整 `discovery_plan`，也能知道下一個學習閉環是 runtime source reconcile、cost-gate learning activation、MM signal search、Polymarket replay history，還是 formal promotion review。

邊界：source/test/docs only。本輪沒有刷新 runtime artifact、沒有同步 `trade-core`、沒有修改 cron/env、沒有部署/重啟、沒有 PG write、沒有 Bybit private/signed/trading call、沒有下單或降低 Cost Gate。

驗證：alpha discovery focused suite 46 passed。
