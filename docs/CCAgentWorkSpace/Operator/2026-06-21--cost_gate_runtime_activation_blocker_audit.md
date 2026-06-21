# 2026-06-21 -- Cost-Gate Runtime Activation Blocker Audit

只讀 runtime audit 結論：PG reject 數據正在積累，但 learning ledger 沒有積累。

證據：

- `trade-core` source 還在 `917be4cc...`，落後 `origin/main` 5 commits，且 dirty。
- runtime source 缺少新的 `cost_gate_learning_lane/status.py`、`reject_materializer.py`、cron wrapper 和 installer。
- crontab 沒有 cost-gate learning lane 條目。
- `/tmp/openclaw/cost_gate_learning_lane/` 只有舊 plan，沒有 ledger、materializer latest、outcome refresh、blocked review artifacts。
- running engine env 沒有 `OPENCLAW_DEMO_LEARNING_LANE_WRITER`。
- PG 近 4h 有 `27071` 條 demo/live_demo Cost Gate rejects，總數 `4423477`，latest `2026-06-21 20:47:59.988+02`。

所以問題不是「沒有數據」；是 runtime 尚未啟動 learning lane，把 PG rejects materialize / append / markout / review。下一步需要你明確授權 runtime source reconcile/sync、cron install、append enablement；若也要 hot-path writer，還需要 env update + approved restart。

本 audit 沒有 pull、沒有改 crontab、沒有改 env、沒有 restart、沒有 append ledger、沒有寫 PG、沒有 Bybit private/signed/trading call、沒有下單、沒有 lower Cost Gate。
