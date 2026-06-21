# Runtime Demo Cost Gate Read-Only Audit

這次只做 read-only runtime audit，沒有改 runtime。

結論：

- demo engine 是活的，不是 engine dead
- 最近 4h 有 2,496 條 demo/live_demo decision/risk rows
- 這 2,496 條全部是 `cost_gate_js_demo_negative_edge`
- 最近 4h intents/orders/fills 都是 0
- 最近 24h 有 53,597 條 decision/risk rows，但只有 3 個 intents/orders、0 fills
- audit 時最近 1h 所有 decision/risk/order/fill row 都是 0；最後一筆 decision/risk 是 `2026-06-21 23:15:59.991+02`
- runtime alpha artifact 還是舊 `alpha_discovery_runtime_killboard_v1`，仍 false-report `actionable_alpha_found=true` / `actionable_probe_found=true`
- runtime source 仍是 `behind 5` 且 dirty/untracked，HEAD `917be4cc`
- demo-learning evidence cron 和 Cost Gate learning lane cron 都沒裝
- Cost Gate learning lane 只有舊 plan artifact，沒有 heartbeat/status/ledger/outcome/review loop

所以目前 demo 很久沒下單的主要事實鏈是：

`engine alive -> candidates hit Cost Gate -> rejects are recorded -> no intents/orders/fills -> learning lane not active -> stale alpha artifact falsely says actionable`

這表示拒單不是完全 silent drop；Risk/Cost Gate record layer 有記錄。但它沒有形成真正的自主學習閉環，因為 learning lane 沒跑，blocked outcome review 沒持續刷新，demo order/fill 驗證也沒有產生。

下一步應該是 operator 授權的 runtime source reconcile，然後跑 demo-learning evidence cron 與 Cost Gate learning-lane activation preflight/install。這一步不等同於降低 Cost Gate，也不授權下單 probe。

邊界：本輪沒有 sync runtime、沒有刷新 artifact、沒有改 crontab/env、沒有 deploy/restart、沒有寫 PG、沒有連 Bybit、沒有下單、沒有降低 Cost Gate。
