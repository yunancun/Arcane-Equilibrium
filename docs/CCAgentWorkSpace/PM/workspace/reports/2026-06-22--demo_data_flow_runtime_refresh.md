# Demo Data Flow Runtime Refresh

日期：2026-06-22
角色：PM
範圍：read-only `trade-core` PG refresh；不寫 DB，不改 runtime。

## 結論

demo/live_demo 並沒有完全停止，也沒有看到 risk-recording 層 silent drop 的證據。最近 1h 仍有 2355 條 decision/risk rows，且最新時間到 `2026-06-22 03:38:59.997+02`。但它們全部被 Cost Gate 拒絕，0 intents/orders/fills。

更長窗口也一樣：24h 有 61,093 條 risk verdicts，其中 61,090 條 rejected；只有 3 條 approved，對應 3 條 demo `flash_dip_buy` PostOnly Working orders，0 fills。這說明我們有足夠的 reject data 去做 blocked-signal counterfactual/review，但真實下單/成交樣本仍遠遠不足，不應直接全局降低 Cost Gate。

## Pipeline Counts

| lookback | decision_features | rejected_features | risk | approved | rejected | intents | orders | fills | latest feature/risk | latest order |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1h | 2355 | 2355 | 2355 | 0 | 2355 | 0 | 0 | 0 | `2026-06-22 03:38:59.997+02` | |
| 4h | 7637 | 7634 | 7637 | 3 | 7634 | 3 | 3 | 0 | `2026-06-22 03:38:59.997+02` | `2026-06-22 02:00:00.655+02` |
| 24h | 61093 | 61090 | 61093 | 3 | 61090 | 3 | 3 | 0 | `2026-06-22 03:38:59.997+02` | `2026-06-22 02:00:00.655+02` |

## Top Risk Reasons

1h:

- `cost_gate(JS-demo): edge=3.61bps < threshold=8.80bps (fee=4.00bps, wr=0.59)`：2355

4h:

- `cost_gate(JS-demo): estimated=-6.01bps < 0`：2696
- `cost_gate(JS-demo): estimated=-2.73bps < 0`：2583
- `cost_gate(JS-demo): edge=3.61bps < threshold=8.80bps (fee=4.00bps, wr=0.59)`：2355
- approved empty-reason rows：3

24h:

- `cost_gate(JS-demo): estimated=-2.74bps < 0`：39637
- `cost_gate(JS-demo): estimated=-6.01bps < 0`：16515
- `cost_gate(JS-demo): estimated=-2.73bps < 0`：2583
- `cost_gate(JS-demo): edge=3.61bps < threshold=8.80bps (fee=4.00bps, wr=0.59)`：2355
- approved empty-reason rows：3

## Recent Orders

All 24h orders are demo `flash_dip_buy` PostOnly Limit Working orders:

| ts | symbol | side | status | order_id |
|---|---|---|---|---|
| `2026-06-22 02:00:00.655+02` | `BNBUSDT` | Buy | Working | `oc_dm_1782086400003_6` |
| `2026-06-22 02:00:00.180+02` | `XRPUSDT` | Buy | Working | `oc_dm_1782086400002_5` |
| `2026-06-22 02:00:00.004+02` | `ETCUSDT` | Buy | Working | `oc_dm_1782086400001_4` |

No fills were recorded in 1h/4h/24h.

## Interpretation

- Reject records exist, so the immediate fear that Cost Gate rejections are silently discarded is not supported by this runtime PG evidence.
- Current data volume is enough to support counterfactual review of blocked signals.
- Current order/fill volume is not enough to learn execution/PnL from actual demo orders.
- Lowering Cost Gate globally is not justified by this snapshot; the safer path is bounded demo-learning/probe review after source reconcile.

## Boundary

Performed:

- `ssh trade-core` read-only PG SELECTs
- `PGOPTIONS=-c default_transaction_read_only=on`

Not performed:

- no runtime source sync
- no cron install
- no env edit
- no deploy/rebuild/restart
- no PG write/schema migration
- no Bybit private/signed/trading call
- no credential/auth/risk/order/strategy mutation
- no Cost Gate lowering
- no order/probe authority
- no promotion proof
