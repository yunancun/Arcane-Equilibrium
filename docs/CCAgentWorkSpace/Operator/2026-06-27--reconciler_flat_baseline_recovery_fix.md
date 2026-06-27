# Operator Note — Reconciler Flat Baseline Recovery Fix

狀態：`DONE_WITH_CONCERNS`

修正內容：Rust `position_reconciler` 不再把「baseline 空、current 也空」當成要重播種並跳過的狀態，而是視為乾淨驗證週期。這讓 Guardian 的 reconciler recovery 可以在空倉後累積 clean cycles。

已部署到 Demo runtime：

- Code/runtime: `724c78b5a6c9213a60baa1c4a26633d55342d079`
- Runtime tests: `56 passed`
- Engine restart: `2432529 -> 3795702`
- API/watchdog 未重啟：`3727506` / `1538268`
- Post-deploy log check：warmup seeded `0`，沒有再看到空倉 `baseline reseeded` tail。

風控語義保持不變：GUI `10.0%` 仍是 per-trade risk percent，不是 `10 USDT`。單筆 cap 仍由 GUI per-trade cap、GUI max single position budget、Guardian adjusted cap 取 min。

注意：post-restart Guardian 目前是 `NORMAL`，但這是部署重啟後狀態，不可直接當 admission proof。下一步仍需要 fresh active current-candidate Demo Decision Lease 和 fresh gate evidence；本輪沒有下單、沒有 lease mutation、沒有 Cost Gate/risk expansion、沒有 live/mainnet。
