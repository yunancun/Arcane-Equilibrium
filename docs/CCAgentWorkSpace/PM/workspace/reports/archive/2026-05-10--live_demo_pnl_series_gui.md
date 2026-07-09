# Live/Demo PnL Series GUI Fix

Date: 2026-05-10
Role: PM local implementation checkpoint

## Scope

- Removed the duplicated `net_pnl_today` card from the shared Performance Metrics list. Live/Demo keep one Today PnL surface in their PnL overview/sidebar, backed by `account_metrics_today`.
- Added read-only DB-backed PnL series endpoints:
  - `GET /api/v1/strategy/demo/pnl-series?range=1h|6h|24h|7d|30d`
  - `GET /api/v1/live/pnl-series?range=1h|6h|24h|7d|30d`
- Replaced Live/Demo chart sourcing from "last 50 fills" with bucketed `realized_pnl - fee + funding` series and a compact bucket table.

## Grafana / TradingView Finding

- Grafana can embed panels via iframe, but official docs tie embedded access to viewer permissions or anonymous access, and `allow_embedding=false` is the default security setting. Grafana Cloud also does not support panel embedding with anonymous access. Directly iframing Grafana here would add auth/CSP/public-dashboard coupling.
- TradingView Advanced widgets are easy iframe embeds for market symbols, but custom PnL series requires Advanced Charts with a custom Datafeed API. TradingView docs state the charting library does not include market data and the app must provide a datafeed. Lightweight Charts is open-source and custom-data friendly, but still requires our backend series.
- Decision: implement the backend series first and keep the UI native. This preserves auth, avoids an external iframe, and can later feed Lightweight Charts if we want a richer TradingView-like renderer.

Sources:
- https://grafana.com/docs/grafana/latest/dashboards/share-dashboards-panels/
- https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/
- https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/table/
- https://www.tradingview.com/charting-library-docs/latest/connecting_data/datafeed-api/
- https://www.tradingview.com/lightweight-charts/

## Verification

- `python3 -m py_compile .../app/pnl_series.py .../app/trading_true_metrics.py .../app/strategy_ai_routes.py .../app/live_session_account_routes.py`
- `python3 -m pytest .../tests/test_pnl_series.py .../tests/test_trading_true_metrics.py .../tests/test_performance_metrics_gui_contract.py -q` -> 14 passed
- `python3 -m pytest .../tests/static/test_replay_subtab_static_assets.py -q` -> 51 passed
- `node --check .../app/static/common.js`
- embedded script parse check for `tab-demo.html`, `tab-live.html`, `console.html`
- `git diff --check`

## Boundary

- No restart.
- No rebuild.
- No DB migration.
- No live auth mutation.
- No strategy/risk parameter change.
