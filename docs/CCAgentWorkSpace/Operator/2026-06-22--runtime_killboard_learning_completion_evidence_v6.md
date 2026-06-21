# Runtime Killboard Learning Completion Evidence v6

這批把 learning worklist 的「怎樣才算完成」鏡像到 runtime killboard/history。

變更：

- runtime killboard schema 升到 `alpha_discovery_runtime_killboard_v6`
- killboard/history 新增 top learning task 的：
  - completion gate
  - completion status
  - completion evidence required count
  - compact evidence
  - evidence key count
  - 若 top task 是 Cost Gate blocked-review，會鏡像 top side-cell / wrongful-block score / net cost cushion

這樣看 runtime artifact 時，不用解析完整 worklist 也能知道下一個 learning task 是什麼、需要什麼證據才算做完、以及最值得 review 的被擋信號是哪個。

驗證：

- `test_alpha_discovery_throughput.py` + `test_alpha_discovery_learning_worklist.py`：48 passed
- focused `py_compile`：passed

邊界：本輪只改 source/test/docs；沒有 runtime sync、沒有刷新 artifact、沒有裝 cron、沒有啟 writer、沒有寫 PG、沒有連 Bybit、沒有下單、沒有降低 Cost Gate。
