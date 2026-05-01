# TODO Continue: Scanner Context + GUI Performance Metrics

Date: 2026-05-01
Status: Source checkpoint complete; PRE-LIVE-3 partial

## Summary

- `be8fe37` exposes Rust scanner context to Python control-plane surfaces.
  - `/scanner/opportunities` now preserves legacy GUI fields and adds `scanner_context`, strategy `fitness`, `breakout_proxy`, and fail-soft `strategy_judgments`.
  - ScoutWorker reads Rust scanner opportunities first, then falls back to the legacy Python scanner stub.
  - `V034__mlde_scanner_context_columns.sql` adds scanner trend/fitness columns to the MLDE training view source file.
  - MLDE shadow advisor and DreamEngine include scanner context in advisory payloads.
- `569e06b` unifies Demo/Paper/Live GUI performance metrics.
  - Backend emits one canonical metric list for 24h/7d PnL, fees, AI cost, edge quality, drawdown, Sharpe, and holding time.
  - Demo/Paper/Live tabs render the shared metric list with one formatter and tooltip contract.

## Verification

- `python3 -m py_compile ...` for touched Python modules.
- Scanner/API targeted pytest: 15/0.
- GUI performance metric contract: 10/0.
- MLDE shadow advisor / DreamEngine targeted: 5/0.
- Paper metrics: 23/0.
- Live endpoint actual-engine: 17/0.
- Phase2 route coverage standalone: 43/0.
- Static JS syntax check: 10 scripts.
- `git diff --check`.
- V034 was applied twice against a local temporary Postgres cluster; a sample row verified `scanner_market_regime`, `scanner_trend_phase`, `scanner_trend_score`, and `scanner_f_bkout`.

## Runtime

- Linux source is synced to `569e06b`.
- Watchdog: `engine_alive=true`; demo/live alive; paper inactive by design.
- Passive wrapper at 2026-05-01 22:51 CEST: SUMMARY WARN exit 0.
  - Existing WARNs remain: `[4]`, `[10]`, `[22]`, `[27]`, `[33]`, `[38]`, `[40]`, `[41]`, `[11]`, `[16]`.
  - `[22]` remains maker no-fill context with `working_maker_orders_1h=3`.
  - `[27]` remains rejected-only risk/cost-gate context with `approved_verdicts_30m=0`.

## Boundary

- No Rust rebuild/restart was performed.
- No runtime DB migration apply was performed.
- No live authorization, risk config, strategy parameter, cron, SIGHUP, HTTPS deploy, or true-live action was performed.
- PRE-LIVE-3 is not fully complete: canonical metrics are done; [33]/[38]/[40] trend charts and Live readiness checklist remain.

