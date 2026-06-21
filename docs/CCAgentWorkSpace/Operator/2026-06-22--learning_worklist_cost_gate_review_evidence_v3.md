# Learning Worklist Cost Gate Review Evidence v3

這批把 v362 的「最像錯殺盈利機會」直接接進 learning worklist。

變更：

- `alpha_learning_worklist` schema 升到 `alpha_learning_worklist_v3`
- Cost Gate outcome/probe review task 的 `evidence` 會帶：
  - top blocked side-cell
  - top review candidate side-cell
  - wrongful-block score
  - net cost cushion
  - blocked-review schema/status
- 如果 Cost Gate task 已到 operator probe review 階段，objective 會明確變成 `operator_review_top_blocked_signal_side_cell_before_bounded_demo_probe`

這不會降低 Cost Gate，也不授予 probe/order 權限。它只是讓之後 autonomous learning worklist 能直接指出最值得人工/QC review 的被擋信號。

驗證：

- `test_alpha_discovery_learning_worklist.py`：3 passed
- `test_alpha_discovery_throughput.py`：44 passed
- focused `py_compile`：passed

邊界：本輪只改 source/test/docs；沒有 runtime sync、沒有刷新 artifact、沒有裝 cron、沒有啟 writer、沒有寫 PG、沒有連 Bybit、沒有下單、沒有降低 Cost Gate。
