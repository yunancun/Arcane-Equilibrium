# Demo Fast-Balance Equity Artifact Source

狀態轉移：`DONE_WITH_CONCERNS`。

本輪完成 source producer，不是 runtime capture：

- 新增 `demo_fast_balance_equity_artifact.py`，把 `/api/v1/strategy/demo/balance?fast=1` 的 `rust_snapshot_fast` payload 包成 `demo_account_equity_artifact_v1`。
- READY 要求 Demo、paper envelope、`rust_engine`、`connected`、正值 equity、無 Bybit/PG/order/risk/runtime/Cost Gate/authority/proof 污染。
- `current_cap_staircase_risk_worksheet.py` 現在只接受 status `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY` 的 equity artifact。
- 測試直接覆蓋你的修正：GUI `10%` 在 equity `200` 下 resolve 成 `20.0 USDT`，舊 `cap_usdt=10` 只保留為 construction 診斷，不是風控權威。

驗證：focused `22 passed`，完整 `test_cost_gate_*.py` `510 passed`，py_compile pass，`git diff --check` pass。

本輪沒有 runtime/control API capture、沒有 Bybit/API/private call、沒有 PG、沒有下單、沒有 Cost Gate lowering、沒有 risk expansion、沒有任何 probe/order/live authority 或 profit proof。

下一步仍是 PM -> E3 -> BB no-order review：cache-only Demo fast-balance artifact capture + current-candidate construction refresh/reconcile；若 artifact 或 current-candidate scope 不能機器驗證，就標 `BLOCKED_BY_LOSS_CONTROL`。
