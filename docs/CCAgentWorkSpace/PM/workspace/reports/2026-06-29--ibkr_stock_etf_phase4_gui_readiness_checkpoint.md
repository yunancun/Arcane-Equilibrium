# IBKR Stock/ETF Phase 4 GUI Readiness Checkpoint

Date: 2026-06-29
Status: **DONE_WITH_BOUNDARY - display-only GUI readiness surface**
Scope: FastAPI readiness endpoint + console Stock/ETF IBKR status tab.

## Result

Phase 4 now has an operator-visible, display-only readiness surface:

- `stock_etf_routes.py` adds `GET /api/v1/stock-etf/readiness`, a read-only envelope that queries only the local Rust IPC fixture method `stock_etf.get_readiness`.
- The route fails closed when IPC is unavailable and returns `degraded=true`, `first_ibkr_contact_allowed=false`, `stock_live_disabled=true`, and `paper_order_entry_visible=false`.
- The route normalizes any forbidden runtime flag (`ibkr_call_performed`, `secret_slot_touched`, `order_routed`, `bybit_ipc_reused`) into `contract_violation_blocked`.
- `console.html` now shows a static `lane crypto_perp` badge and registers a core `Stock/ETF IBKR` tab.
- `tab-stock-etf.html` displays lane boundary, Phase 2 gate, runtime guard, and denied surface state using only `GET /api/v1/stock-etf/readiness`.
- Static tests assert the tab contains no POST, no submit/cancel method, and no localStorage/sessionStorage lane authorization.

This gives the operator a clear IBKR/Bybit distinction without introducing a GUI lane selector or any effect-capable IBKR path.

## Hard Boundary

This checkpoint does not create a PASS artifact, read or create secret slots, inspect secret contents, start IB Gateway/TWS, open IBKR sockets, or authorize:

- IBKR API call or healthcheck
- IBKR connector implementation
- broker-paper order submission/cancel/replace
- active DB migration apply
- GUI lane authority or login-success lane selection
- evidence clock start
- live, tiny-live, margin, short, options, CFD, transfer, account-management writes, or Client Portal Web API usage

Bybit routes and existing paper/live tabs remain unchanged except for the new console tab registration and static default-lane badge.

## Verification

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/stock_etf_routes.py` - pass
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py` - pass
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py -q` - 8 passed
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_engine_capabilities_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py -q` - 16 passed
- Node inline-script syntax check for `tab-stock-etf.html` - checked 2 inline scripts
- Node inline-script syntax check for `console.html` - checked 1 inline script
- `git diff --check` - pass

## Next Gate

First IBKR contact remains blocked. The next runtime-relevant gate is still real secret/topology evidence plus an immutable Phase 2 PASS artifact. GUI work after this must remain display-only unless backend route/cache/auth partition tests and the ADR-0048 release packet explicitly authorize the next slice.
