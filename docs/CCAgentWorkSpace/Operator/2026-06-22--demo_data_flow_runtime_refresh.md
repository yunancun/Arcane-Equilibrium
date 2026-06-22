# Demo Data Flow Runtime Refresh

日期：2026-06-22
角色：PM
範圍：read-only `trade-core` PG refresh；不寫 DB，不改 runtime。

## 結論

demo/live_demo 仍在累積資料，Cost Gate 拒單也有記錄；沒有看到 risk-recording 層 silent drop。最近 1h 有 2355 條 decision/risk rows，全被 Cost Gate 拒絕，0 intents/orders/fills。最近 24h 有 61,093 條 risk verdicts，其中 61,090 rejected，只有 3 approved/intents/orders，0 fills。

判斷：我們有足夠 reject data 做 blocked-signal counterfactual/review，但沒有足夠真實 demo order/fill data 支撐學習。下一步仍是 source reconcile → bounded learning lane/counterfactual review → operator review bounded demo probe；不應全局降低 Cost Gate。

## 關鍵數字

| lookback | decision/risk | rejected | approved | intents | orders | fills |
|---:|---:|---:|---:|---:|---:|---:|
| 1h | 2355 / 2355 | 2355 | 0 | 0 | 0 | 0 |
| 4h | 7637 / 7637 | 7634 | 3 | 3 | 3 | 0 |
| 24h | 61093 / 61093 | 61090 | 3 | 3 | 3 | 0 |

Latest feature/risk timestamp：`2026-06-22 03:38:59.997+02`。

Top 1h reason：`cost_gate(JS-demo): edge=3.61bps < threshold=8.80bps (fee=4.00bps, wr=0.59)`，2355 條。

24h 只有三張 demo `flash_dip_buy` PostOnly Working orders：`BNBUSDT`、`XRPUSDT`、`ETCUSDT`，時間約 `2026-06-22 02:00:00+02`，0 fills。

## 邊界

只做 `ssh trade-core` read-only PG SELECT，並設 `PGOPTIONS=-c default_transaction_read_only=on`。未做 source sync、cron/env/deploy/restart、PG write、Bybit private call、order/risk/strategy mutation、Cost Gate lowering 或 probe/order authority。
