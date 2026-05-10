# Live/Demo PnL Series Refresh Fix

Date: 2026-05-10

## Scope

- Fixed the no-row PnL bucket display when the running API has not yet loaded the new `/pnl-series` route by falling back to `/fills?limit=200&offset=0`.
- Kept the fallback range-aware, so `1H/6H/24H/7D/30D` still filters recent fills by the selected window.
- Reduced refresh flicker by preserving existing DOM until fresh data is available and avoiding repeated same-HTML rewrites.
- Preserved Live Today PnL values on transient metrics fetch failure.

## Verification

- `python3 -m pytest .../tests/static/test_replay_subtab_static_assets.py -q` -> 52 passed
- `python3 -m pytest .../tests/test_pnl_series.py .../tests/test_trading_true_metrics.py .../tests/test_performance_metrics_gui_contract.py -q` -> 14 passed
- `node --check .../app/static/common.js`
- embedded script parse check for `tab-demo.html`, `tab-live.html`, `console.html`
- `git diff --check`

## Boundary

- Source/static fix only.
- No restart.
- No rebuild.
- No DB migration.
- No live auth mutation.
