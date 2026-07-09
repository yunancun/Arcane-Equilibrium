# TODO Continue: Scanner Context + GUI Performance Metrics

Date: 2026-05-01
Status: Source checkpoint complete; PRE-LIVE-3 partial

## Summary

- `be8fe37` exposes Rust scanner context to Python control-plane surfaces.
  - `/scanner/opportunities` now preserves legacy GUI fields and adds scanner context, strategy fitness, breakout proxy inputs, and fail-soft strategy judgments.
  - ScoutWorker reads Rust scanner opportunities before falling back to the legacy Python scanner stub.
  - V034 migration file adds scanner trend/fitness columns to the MLDE training view source file; runtime DB apply was not performed.
  - MLDE shadow advisor and DreamEngine include scanner context in advisory payloads.
- `569e06b` unifies Demo/Paper/Live GUI performance metrics.
  - Backend emits one canonical metric list for 24h/7d PnL, fees, AI cost, edge quality, drawdown, Sharpe, and holding time.
  - Demo/Paper/Live tabs render the shared metric list with one formatter and tooltip contract.

## Verification

- Python compile for touched modules.
- Scanner/API targeted pytest: 15/0.
- GUI performance metric contract: 10/0.
- MLDE shadow advisor / DreamEngine targeted: 5/0.
- Paper metrics: 23/0.
- Live endpoint actual-engine: 17/0.
- Phase2 route coverage standalone: 43/0.
- Static JS syntax check: 10 scripts.
- `git diff --check`.
- V034 local temporary Postgres idempotency: applied twice, sample scanner fields selected successfully.

## Runtime And Boundary

- Linux source synced to `569e06b`.
- Watchdog alive; wrapper SUMMARY WARN exit 0 at 22:51 CEST.
- No Rust rebuild/restart, runtime DB migration apply, live authorization change, risk config change, strategy parameter change, cron install, SIGHUP, HTTPS deploy, or true-live action.
- Remaining safe TODO candidates: P03-PREP-1, DOC-1, TEST-1, PRE-LIVE-1, or PRE-LIVE-3 trend charts + Live readiness checklist.

