# Cap-Feasible Selector Runtime Sync

Date: 2026-06-26 07:50 CEST

完成一個 runtime hygiene checkpoint：

- Linux runtime source 已從 `0246b263...` fast-forward 到 `b9836224...`。
- crontab expected-head 已只做 SHA literal replacement：old `5 -> 0`，new `0 -> 5`，line count 仍是 `70`。
- API service 沒重啟，MainPID 仍是 `2218842`。
- 沒有 Bybit call、order/cancel/modify、PG write、manual cron run、artifact latest refresh、adapter/writer enablement、Cost Gate/cap/risk mutation、probe/order/live authority。

重要限制：

- 最新 authorization artifact 仍是 sync 前的 ETH Buy defer/no-authority：sha `cdf20e57...`，mtime `2026-06-26 07:45:04 +0200`。
- 我沒有手動跑整條 cost-gate cron，因為那會覆寫多個 `_latest` artifact 並 append JSONL ledger；本 checkpoint 的必要目標只是把已測過的 selector fix 落到 runtime。

下一步：

- 等第一個 post-sync cost-gate cron artifact delta 出現後，執行 `P0-BOUNDED-PROBE-AUTHORIZATION-AVAX-LATEST-CHAIN-REFRESH-REVIEW`。
- 若 post-sync chain 仍指向 ETH，下一步是檢查 selector input path，而不是授權下單。
