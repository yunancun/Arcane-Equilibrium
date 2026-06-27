# Aligned ETH Runtime Admission Review

狀態轉移：`BLOCKED_BY_LOSS_CONTROL`。

E3/BB 都同意只能跑 timestamped noncanonical diagnostic，不能 promotion `_latest`、不能 runtime admission、不能 plan consumer、不能下單。

PM 產生的診斷 artifact：

```text
/tmp/openclaw/aligned_eth_runtime_admission_review_20260627T000135Z/bounded_probe_plan_inclusion_review.json
```

結果：

- status: `CONSTRUCTION_PREVIEW_NOT_READY`
- manifest problems: `[]`
- active probe/order authority: `false/false`
- adapter enabled: `false`
- latest overwrite / plan mutation / ledger append: `false`
- Bybit / PG / order path: `false`

阻塞原因：

```text
ETHUSDT Buy 在 10 USDT per-order cap 下不可構造。
min_positive_qty_notional_usdt=15.7105 > cap_usdt=10.0
```

目前 canonical auth latest 仍是：

```text
status=READY_FOR_OPERATOR_AUTHORIZATION_REVIEW
decision=defer
auth_object_present=false
sha=8056a8598f28aa53b0631ad493aac55d3cac75cd0da81e99f3f5eaf160cc91a3
```

本輪沒有 Bybit call、沒有 order/cancel/modify、沒有 PG write/query、沒有 service restart、沒有 crontab edit、沒有 Cost Gate lowering、沒有 live/mainnet、沒有 profit/proof claim。

下一步：`P0-CAP-FEASIBLE-CANDIDATE-ROTATION-OR-ETH-CONSTRUCTION-REFRESH-REVIEW`。不擴 cap；只審 fresh ETH no-order construction refresh，或 rotate 到 cap-feasible candidate 並重建 reviewed loss-control envelope。
