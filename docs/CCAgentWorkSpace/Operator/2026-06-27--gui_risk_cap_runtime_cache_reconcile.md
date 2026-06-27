# GUI Risk Cap Runtime Cache Reconcile

狀態轉移：`DONE_WITH_CONCERNS`。

本輪做了 runtime cache-only 檢查，沒有下單：

- Runtime bounded auth 最新仍是 `grid_trading|AVAXUSDT|Sell`，status `FALSE_NEGATIVE_PREFLIGHT_NOT_READY`，decision `defer`，沒有 active probe/order authority。
- `trade-core` 本機用 0600 token 讀 `/api/v1/strategy/demo/balance?fast=1` 成功，回 `rust_snapshot_fast / connected`。
- Demo equity 是 `9552.43426257`。
- 生成 accepted artifact：`/tmp/openclaw/gui_risk_cap_runtime_cache_reconcile_20260627T0135Z/demo_account_equity_artifact_ready.json`，sha `afea4d759ab28e7063be23c58de17c3a45007397f7121654aaa7c2e8a044485e`。

用 GUI risk TOML + 這份 equity artifact 跑 worksheet：

- GUI P1 risk/trade = `10.0%`
- per-trade budget = `955.24342626 USDT`
- max single position budget = `2388.10856564 USDT`
- resolved cap = `955.24342626 USDT`

這已用 runtime evidence 證明：GUI 的 `10.0` 是 `10%`，不是 `10 USDT`。

但整體 worksheet 仍 fail-closed：`CONTROL_IDENTITY_CONTRACT_INPUT_NOT_READY`。原因是 current control identity / construction preview 缺失；現有 AVAX reroute/market snapshot/construction 是 2026-06-24 stale，cap-feasible selection 是 2026-06-25 stale，不能拿來當 current construction evidence。

本輪沒有 Control API POST、沒有 Bybit/private/order/cancel/modify、沒有 PG、沒有 service/crontab/env mutation、沒有 runtime sync、沒有 Cost Gate lowering、沒有 risk expansion、沒有任何 probe/order/live authority 或 profit proof。

下一步：不要重複抓 equity；要嘛 runtime source sync 讓 `trade-core` 有 v605 helper，要嘛開 PM -> E3 -> BB no-order public quote/current-construction refresh，產生 fresh current-candidate construction inputs。
