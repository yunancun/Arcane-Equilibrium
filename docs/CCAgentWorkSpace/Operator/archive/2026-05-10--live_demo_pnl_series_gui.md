# Live/Demo PnL Series GUI Fix

Date: 2026-05-10

- Removed the duplicated Today PnL metric card from Live/Demo Performance Metrics; Today PnL now remains in the PnL overview/sidebar only.
- Added read-only `/pnl-series` endpoints for Demo and Live, backed by DB `realized_pnl - fee + funding`.
- Changed Live/Demo charts from "last 50 fills" to selectable ranges: `1H`, `6H`, `24H`, `7D`, `30D`, with a compact bucket table under the chart.
- Chose native backend series instead of Grafana iframe or full TradingView integration. Grafana embedding has auth/anonymous-access/`allow_embedding` constraints; TradingView custom PnL requires a datafeed. The new endpoint can later feed TradingView Lightweight Charts if needed.
- Verified with targeted Python tests, static tests, JS syntax parse, `py_compile`, and `git diff --check`.
- No restart, no rebuild, no DB migration, no live auth mutation.
