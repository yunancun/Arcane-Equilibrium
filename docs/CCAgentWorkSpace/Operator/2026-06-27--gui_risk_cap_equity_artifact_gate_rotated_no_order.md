# GUI Risk Cap Equity Artifact Gate

狀態轉移：`ROTATED`。

本輪確認兩件事：

- Runtime `_latest` 已在 `2026-06-27T00:45Z` 旋回 `grid_trading|AVAXUSDT|Sell`，所以 ETH-specific construction refresh 不再是 current path。
- GUI risk cap resolver 現在不接受裸 `account_equity_usdt` 當權威。必須提供 `demo_account_equity_artifact_v1`，包住 `/api/v1/strategy/demo/balance?fast=1` 的 `rust_snapshot_fast` output，且 timestamp fresh、Demo、connected、正值 equity、無 authority 污染。

已改：

- `current_cap_staircase_risk_worksheet.py` 新增 `--account-equity-artifact-json`。
- 裸 `--account-equity-usdt` 會 fail closed；它只能用來 cross-check artifact。
- Output 會記錄 equity artifact provenance、age、sha、blocking reasons。
- TODO active blocker 已改成 current-candidate drift reconcile；ETH refresh row 已標 `ROTATED`。

驗證：focused `12 passed`，相鄰 suite `113 passed`，py_compile pass。CLI smoke 證明裸 equity 被拒，帶 fast-snapshot equity artifact 的 ETH fixture 才 resolved `20.0 USDT`，但仍是 no-authority/no-order。

本輪沒有 runtime sync、沒有 Bybit/API/private call、沒有 PG、沒有下單、沒有 Cost Gate lowering、沒有 risk expansion、沒有任何 probe/order/live authority。

下一步：只開一個 PM -> E3 -> BB no-order review，範圍是 cache-only Demo fast-balance equity artifact capture + current-candidate no-order construction refresh/reconcile。若 equity artifact 或 current-candidate scope 不能機器驗證，就標 `BLOCKED_BY_LOSS_CONTROL`。
