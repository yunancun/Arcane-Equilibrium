# 2026-07-01 — Stock/ETF Python/GUI Surface Coverage Static Guard

## Scope

PM added a source-only static guard for Stock/ETF/IBKR Python and static GUI guard candidate
coverage.

This is not a FastAPI behavior change, not a GUI behavior change, not connector runtime wiring, not
IBKR contact, not secret access, not paper order routing, and not a Bybit behavior change. It only
locks the file-selection surface used by existing no-write/no-runtime/no-background guards.

## Guard Added

- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_surface_coverage_static_guard.py`

The guard pins:

- all current `app/*stock_etf*.py` and `app/*ibkr*.py` control-api modules are included by the
  Stock/ETF control-api Python candidate scanner;
- all current `program_code/broker_connectors/ibkr_connector/**/*.py` connector skeleton files are
  included by the broader Stock/ETF/IBKR Python scanner;
- all current `app/static/tab-stock-etf*` files are included by the static GUI scanner;
- no selected candidate path includes Bybit runtime module fragments such as REST client, private
  WS, order manager/router, or bounded-probe active-order code.

## Verification

- New control-api guard py_compile: PASS.
- Focused new guard pytest: `4 passed`.
- Full Stock/ETF control-api pytest: PASS.
- Docs PM trace tests: PASS.
- Diff check: PASS.

## Boundary

No IBKR SDK import, no socket/HTTP, no secret read or creation, no connector runtime, no read-only
probe, no result import, no evidence or scorecard writer, no DB apply, no paper order route, no
tiny-live/live authorization, and no Bybit live/demo execution change.
