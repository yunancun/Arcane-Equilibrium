# Live/Demo GUI 今日 PnL 口徑修正

Date: 2026-05-10
Owner: PM

## Summary

Live GUI / console 側欄的「今日淨 PnL」錯用了前端推算：`unrealized + realized - engine_total_fees`，其中 `engine_total_fees` 是 session/lifetime 累計 bucket。這會把總手續費/總虧損混入今日欄位，形成 operator 看到的約 `-45.45` 類錯值。

## Runtime Verification

Linux `trade-core` read-only DB query:

- `live_demo today_db_tz`: fills 28, gross `+1.875740`, fees `0.296851`, net `+1.578890`
- `live_demo rolling_24h`: net `+1.584620`
- `live_demo rolling_7d`: net `-0.549938`
- `live_demo lifetime`: gross `+9.617450`, fees `45.711300`, net `-36.093800`

Conclusion: 今日 LiveDemo 不是 `-45.45`；舊 GUI 混入了累計 fee bucket。

## Changes

- Added backend `account_metrics_today` and canonical `net_pnl_today`.
- Live tab PnL overview now reads `/api/v1/live/metrics` for today realized/net PnL.
- Console Live sidebar now reads the same `net_pnl_today`.
- Added static frontend/backend tab contract tests for Demo vs Live endpoints.

## Verification

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_performance_metrics_gui_contract.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_trading_true_metrics.py -q` — 10 passed
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_replay_subtab_static_assets.py -q` — 50 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/trading_true_metrics.py` — PASS

## Boundary

No restart, no rebuild, no DB migration, no live auth mutation, no strategy/risk config change, no true-live authority change.
