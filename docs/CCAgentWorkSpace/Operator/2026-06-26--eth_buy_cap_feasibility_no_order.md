# Operator Note: ETH Buy Cap Feasibility No-Order

Date: 2026-06-26 07:04 CEST

本輪結論：`grid_trading|ETHUSDT|Buy` 是高 upside 研究線索，但不能在現有 `10 USDT` bounded cap 下執行。最新 construction preview 顯示最小可執行 notional 是 `15.7105 USDT`，cap 下 rounded qty 是 `0`，所以不能進入 probe/order。

決策：

- 不提高 global Cost Gate。
- 不提高/改寫 runtime cap。
- 不 grant probe/order/live authority。
- 不把 ETH 當作當前 bounded Demo candidate。
- `grid_trading|AVAXUSDT|Sell` 仍是目前唯一已選出的 current-cap-feasible bounded Demo candidate，但仍缺有效授權。

下一個安全可推進項：暫停後從 `P1-AGGRESSIVE-ALPHA-CAP-FEASIBLE-LOW-PRICE-REGIME-FILTER-NO-ORDER` 繼續，只做 source-only regime/filter mining，優先找能留在 `10 USDT` cap 內、且更接近真實費後正 PnL 的候選子集。

本輪沒有 Bybit order/cancel/modify、PG write、runtime mutation、service/crontab/env mutation、Rust writer/adapter enablement、Cost Gate change、live/probe/order authority 或 profit proof claim。
