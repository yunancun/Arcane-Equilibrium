# 2026-06-30 IBKR Stock/ETF GUI Allowlist Readiness Trace Checkpoint

VERDICT: PASS
CONFIDENCE: high

## Result

- The display-only Stock/ETF IBKR static tab now renders the normalized readiness `api_allowlist` payload.
- The new API Allowlist panel shows accepted/blocked status, contract id, source version, read/paper-write/denied action counts, no-contact/no-secret flags, Bybit-live protection proof, and allowlist blockers.
- Allowlist blockers are also merged into the existing denied/blocker surface so operator-visible readiness reflects the same fail-closed contract state as the FastAPI route.
- Static route tests now assert the Stock/ETF tab consumes `api_allowlist` while preserving the no-POST/no-order/no-storage GUI boundary.

## Boundary

- This is a static display-only GUI checkpoint.
- No IBKR contact, healthcheck, socket, connector construction, secret read/create/serialization, paper order, fill import, audit writer, DB apply, GUI authority, lane selector authority, release, Phase 2 start, tiny-live, or live authority was added or exercised.
- No Bybit live execution behavior was changed.
- Linux `trade-core` runtime checkout was not touched or fast-forwarded.

## Verification

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py`
  - passed
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`
  - `12 passed`
- Node inline-script syntax check for `tab-stock-etf.html`
  - checked `2` inline scripts
- `git diff --check`
  - passed

## Dispatch Note

Sub-agent E2 was not spawned because the available sub-agent tool policy allows spawning only when the user explicitly asks for sub-agents or parallel agent work. This checkpoint is narrow, display-only, and covered by static no-write tests plus inline JavaScript syntax parsing.

## Next Gate

Continue Phase 1/4 readiness hardening. Do not proceed to Phase 2 IBKR read-only contact until the immutable external-surface PASS artifact and real secret/topology evidence exist.
