# Operator Note: Cap-Feasible Selector Source Fix

Date: 2026-06-26 07:34 CEST

本轮发现新的 runtime artifact delta：latest scorecard / authorization 又指向 `grid_trading|ETHUSDT|Buy`，但 ETH 在当前 `10 USDT` cap 下仍不可构造；AVAX 仍是 top current-cap-feasible candidate。

已做 source-only 修复：

- cron wrapper 现在可以从 cap-feasible candidate selection artifact 读取 `selected_candidate.side_cell_key`。
- false-negative operator review 会优先用这个 side-cell，再回退 top ranked false-negative。
- 也支持显式 env override：`OPENCLAW_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW_SELECTED_SIDE_CELL_KEY`。

这不会授权、不会下单、不会降低 Cost Gate、不会写 PG、不会改 runtime。它只是避免后续 latest artifact 链继续把 bounded Demo 授权 review 跑到当前 cap 不可执行的 ETH。

验证已过：shell syntax、cron static、bounded authorization/preflight、operator-review focused tests。

下一步如果要让它在 runtime 生效，需要单独走 `PM -> E3` 的 runtime source-sync / expected-head review；本轮未做 runtime sync、未改 crontab、未 restart service。
