# Operator Note: Bounded Probe Operator Authorization Artifact

日期：2026-06-23
Checkpoint：`bbb5c51f`

已完成 source/test/docs + Mac/origin/Linux 三端同步。這輪沒有授權或提交任何 demo 訂單。

新增內容：

- `bounded_probe_operator_authorization.py`：artifact-only builder。
- `bounded_probe_operator_authorization_cli.py`：產生 Markdown/JSON review packet。
- shared contract constants moved to `contract.py`，runtime adapter 引用同一組常數。

authorization object 只會在以下條件全部通過時輸出：

- sealed preflight status `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION`
- placement repair status `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`
- authority-path readiness status `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`
- 三個 artifacts fresh 且 side-cell/horizon/candidate 對齊
- operator id、authorization id 非空
- max authorized probe orders > 0 且不超過 source plan budget
- expiry 未過期且在 TTL cap 內
- typed confirm 精確等於 `authorize_bounded_demo_probe:<side-cell>:<max-orders>:<authorization-id>`

已驗證：

- Mac authorization tests：7 passed
- Mac policy suite：71 passed
- Mac bounded/preflight/operator-review related suite：36 passed
- Linux authorization tests：7 passed
- Linux policy suite：71 passed
- Linux bounded/preflight/operator-review related suite：36 passed

下一個真 gate 仍是 explicit operator review。只有 operator 決定授權後，才應把 packet 內嵌的 `operator_authorization` 放入 future bounded Demo probe plan；之後仍需要 fill/fee/slippage、matched blocked controls、result review、execution-realism review 才能討論任何 Cost Gate 調整。

邊界：no CI, no PG, no Bybit, no deploy/restart, no cron/env/auth/risk/order mutation, no active probe/order authority, no Cost Gate lowering, no actual order, no promotion proof.
