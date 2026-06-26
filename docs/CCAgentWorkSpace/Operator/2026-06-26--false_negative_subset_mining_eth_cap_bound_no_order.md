# False-Negative Subset Mining: ETH Cap-Bound No-Order Packet

Date: 2026-06-26 06:54 CEST

本輪完成 source-only false-negative subset mining，沒有下單、沒有授權、沒有改風控。

結論：

- latest scorecard 的最高 upside 是 `grid_trading|ETHUSDT|Buy`
  - avg modeled net `258.3905bps`
  - `7/7` net-positive
  - friction rank `1`
  - preflight ready
- 但 ETH Buy 在目前 `10 USDT` cap 下不可構造：
  - min executable notional 約 `15.7318 USDT`
  - rounded qty 變成 `0`
  - blocking gates: `min_positive_qty_notional_exceeds_cap`, `rounded_notional_below_min_notional`, `rounded_qty_not_positive_under_cap`
- 因此 ETH Buy 只能進下一個 source-only cap/risk proposal，不能直接變成 bounded Demo order/probe。
- `grid_trading|AVAXUSDT|Sell` 仍是目前唯一 current-cap-feasible bounded Demo candidate，但仍卡在 authorization。

本輪狀態：

- `active_blocker_id`: `P1-AGGRESSIVE-ALPHA-FALSE-NEGATIVE-SUBSET-MINING-NO-ORDER`
- `status`: `DONE_WITH_CONCERNS`
- `next_blocker_id`: `P1-AGGRESSIVE-ALPHA-ETH-BUY-CAP-FEASIBILITY-PROPOSAL-NO-ORDER`

邊界：沒有 Bybit/API/order/cancel/modify call、沒有 PG write、沒有 runtime sync、沒有 service restart/rebuild、沒有 crontab/env mutation、沒有 `_latest` overwrite、沒有 Rust writer/adapter enablement、沒有 Cost Gate 變更、沒有 live/probe/order authority、沒有 proof/promotion claim。
