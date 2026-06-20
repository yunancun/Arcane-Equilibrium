# Polymarket hourly-topn 已啟用

已在 `trade-core` 啟用 Polymarket 每小時 top-50 artifact-only 採集：

- `41 4 * * *` daily 全量仍保留
- `7 * * * *` hourly top-50 已由註釋停用改為 active

手動 smoke 成功：`/tmp/openclaw/polymarket_axis_runs/hourly-topn-20260620T111919Z`，50 events、525 snapshot rows、1 HTTP request、errors 空。這不碰交易、不碰 Bybit、不碰 PG、不碰 secrets、不改 live/demo 參數。

目的：Polymarket 是目前少數未被判死、但缺時序樣本的外部資料軸；hourly lane 是跑 lead-lag forward IC 的必要前置。下一步等 20-30 個 hourly time points 後再做 leak-free IC / residual / regime / HAC 檢驗。

PM 詳報：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-20--polymarket_hourly_topn_activation.md`
