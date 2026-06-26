# Operator Note — ETH Cap Envelope Sensitivity No-Order

Date: 2026-06-26 09:04 CEST

本輪結論：不提高 ETH cap，不開 ETH order/probe path。

`grid_trading|ETHUSDT|Buy` 仍是高 upside research lead，但 current `10 USDT` cap 下不可構建。按現有 construction preview 的 `1571.05` limit price 與 `0.01 ETH` qty step，第一個可執行 tier 是 `0.01 ETH = 15.7105 USDT`，第二個是 `0.02 ETH = 31.4210 USDT`。這是明確 exposure change，不是 placement 小調整。

新 runtime read-only snapshot 也顯示 v557 sync 已反映到 scheduled artifact：`bounded_probe_operator_authorization_latest.json` 現在是正確的 `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`，但仍然是 `defer`、無 typed confirm、無 authorization id/object、無 probe/order authority。

Current bounded Demo candidate 仍是 `grid_trading|AVAXUSDT|Sell`；`P0-BOUNDED-PROBE-AUTHORIZATION` 仍 blocked。按你的要求，這輪做完後暫停，不再自動推進下一個 blocker。
