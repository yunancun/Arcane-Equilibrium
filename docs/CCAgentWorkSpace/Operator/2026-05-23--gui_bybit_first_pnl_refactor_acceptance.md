# GUI Bybit-first Demo PnL Refactor Acceptance

Date: 2026-05-23 13:23 CEST
PM scope: `GUI-TODO.md` Phase 2, operator decisions `1A2A3A`
Status: SOURCE-DONE / REVIEW-APPROVED / DEPLOY-SYNC-PENDING

## Operator Decisions

1. Q1 = A: implement response field only now; no 24h drift cron in this sprint.
2. Q2 = A: no `/demo/wallet-truth` route in this sprint; close only the closed-PnL truth path.
3. Q3 = A: backend keeps four precise `strategy_source` values; GUI folds them into operator-readable labels.

## Delivered Scope

- Added Bybit-first read model at `GET /api/v1/strategy/demo/closed-pnl`.
- Added Bybit REST helper for `GET /v5/position/closed-pnl`, preserving raw `list` and `nextPageCursor`.
- Added process-local `ClosedPnlCache` with TTL and in-flight dedup for identical closed-PnL requests.
- Added read-only PG reconciliation/fallback from `trading.fills` for `demo` and `live_demo` only.
- Added `strategy_source` contract: `pg_fill`, `pg_link_id`, `bybit_unknown`, `pg_missing_unknown_external`.
- Fixed cursor pagination beyond 500 rows and covered it with tests.
- Fixed `oc_ld_*` live-demo link attribution to query the `live_demo` owner map when PG fill match is missing.
- Updated Demo Profit tab to show exchange-confirmed `closedPnl` directly, net of Bybit fees, instead of browser-side round-trip reconstruction.
- Scoped Bybit source/cache/stale UI to the Profit/PnL subtab; non-profit fill tabs now read as PG fills.
- Updated refresh affordance: PG tabs show `刷新成交`; Profit shows `刷新 Bybit PnL` and uses `force_refresh=true`.
- Added `restart_all.sh` engine socket readiness gate before API restart.
- Registered `_CLOSED_PNL_CACHE` in the singleton registry.

## Reviews

- BB Bybit constraints: accepted. Current route uses fixed `linear`, `_get`, cursor pagination, 7-day max window, cache + in-flight dedup, and Bybit failure degrades to stale cache or PG fallback.
- E2 adversarial review round 1: RETURN on 500-row truncation and `oc_ld_*` attribution. Both fixed and tested.
- E3 security/read-only review: APPROVE. Closed-PnL surface is GET-only; PG paths are SELECT-only; no new secret/log leak; Demo GUI remains `demo/live_demo`.
- A3 UX review round 1: RETURN on stale/source scope and operator wording. Fixed.
- A3 UX re-review: APPROVE.

## Verification

Pass:

- `bash -n helper_scripts/restart_all.sh`
- `python3 -m py_compile app/bybit_pnl_cache.py app/bybit_rest_client.py app/strategy_ai_routes.py`
- `node --check app/static/common.js`
- Inline script syntax check: `tab-demo.html` 2 scripts OK, `tab-system.html` 2 scripts OK
- Focused pytest: `tests/test_bybit_rest_client.py tests/test_bybit_closed_pnl_route.py` = 50 passed, 11 existing warnings
- Invariant grep: no new closed-PnL write path; closed-PnL route is GET-only; Bybit helper uses `_get("/v5/position/closed-pnl", ...)`
- E3 read-only/security review APPROVE
- A3 UX re-review APPROVE

Known existing failures observed during broader verification:

- `tests/static/test_replay_subtab_static_assets.py`: 12 failed / 41 passed. Failures are static fixture drift around `tab-live.html` extracting logic into `tab-live.js`, plus console/development label drift; Demo closed-PnL checks were not the failing assertions.
- `PYTHONPATH=. python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1 -q`: 4171 passed / 21 failed / 12 skipped. The 21 failures are existing broad-suite drift, including the static `tab-live.html` extraction mismatch and `test_sweep_orphan_orders_handles_cancel_failure`, whose expected raw reason conflicts with HEAD code already returning stable `order_sweep_cancel_all_failed`.
- Single reruns: `test_replay_routes_safe_query_audit::test_case2_pg_kill_simulation_returns_200_degraded` passed; `test_gui_fast_snapshot_routes::test_demo_and_live_tabs_use_fast_initial_snapshot_paths` failed only on `tab-live.html` static extraction drift.

## Carry-over

- Q1 cron drift monitor remains Sprint 5+ carry-over by operator choice.
- Q2 wallet truth route remains out of scope by operator choice.
- Static test fixture modernization for extracted `tab-live.js` remains separate maintenance work; not caused by this diff.
