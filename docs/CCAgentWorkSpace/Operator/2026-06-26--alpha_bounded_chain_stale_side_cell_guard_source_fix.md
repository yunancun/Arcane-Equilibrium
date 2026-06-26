# Alpha Bounded-Chain Stale Side-Cell Guard Source Fix

Date: 2026-06-26 08:10 CEST

本輪沒有下單、沒有跑 cron、沒有寫 PG、沒有改 runtime、沒有刷新 `_latest`。

結論：

- runtime 上 `08:00:05 CEST` 的 bounded auth latest 仍然是 `grid_trading|ETHUSDT|Buy`、`decision=defer`、無 probe/order authority。
- 但 cap-feasible selection 仍然只有一個：`grid_trading|AVAXUSDT|Sell`，`fits_current_cap=true`。
- 問題在 alpha cron：它優先吃 stale `false_negative_bounded_probe_preflight_latest.json`，所以又把 ETH 往下游 bounded review chain 刷了一輪。
- source fix 已加：如果 cap-feasible selected side-cell 和 bounded preflight side-cell 不一致，alpha cron 會 fail-closed，跳過 bounded review chain，也不把 stale bounded inputs 餵給 scorecard。

驗證：

- `bash -n helper_scripts/cron/alpha_discovery_throughput_cron.sh` PASS
- `python3 -m pytest -q helper_scripts/cron/tests/test_alpha_discovery_throughput_cron_static.py` -> `9 passed`
- `python3 -m pytest -q helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py` -> `15 passed`

下一步：

- 暫停前不做 runtime sync。
- 下個 checkpoint 是 `P1-RUNTIME-HEALTH-HYGIENE-ALPHA-BOUNDED-CHAIN-STALENESS-GUARD-SYNC-REVIEW`：只做 source/crontab expected-head 對齊，不 restart、不手動跑 cron、不碰 Bybit/PG/order/probe authority。
