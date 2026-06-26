# Current-Cap Staircase Risk Worksheet No-Order

本輪把 AVAX `10 USDT` current-cap sizing 做成 source-only helper。沒有交易、沒有 PG、沒有 cron/service 變更、沒有 Cost Gate/cap/risk mutation、沒有 authority/proof claim。

結果：

- 新增 `current_cap_staircase_risk_worksheet.py` + focused tests。
- Smoke：`grid_trading|AVAXUSDT|Sell` 在 `10 USDT` cap 下 constructible。
- 8 個 executable tiers：最小 `0.9 AVAX / 5.4576 USDT`，最大 `1.6 AVAX / 9.7024 USDT`。
- 以 `3` probe orders review cap 計，worst-case reserved `30.0 USDT`，max executable tier reserved `29.1072 USDT`。
- cap/risk mutation required：`false/false`。
- order admission ready：`false`，因為 BBO stale 且沒有 bounded auth。
- P0 bounded authorization 仍 blocked/no-repeat；runtime auth artifact at `2026-06-26T08:15:05Z` still defer/no-authority。

下一步：

- 如果有真 AVAX-scoped auth delta，才進 P0 authorization。
- 否則下一個最快 source-only 落地點是 `P1-AGGRESSIVE-ALPHA-FEE-SLIPPAGE-MAKER-TAKER-SCHEMA-NO-ORDER`。

PM report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--current_cap_staircase_risk_worksheet_no_order.md`.
