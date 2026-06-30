# 2026-06-30 IBKR Stock/ETF FastAPI Readiness Allowlist Gate Checkpoint

VERDICT: PASS
CONFIDENCE: high

## Result

- FastAPI Stock/ETF readiness now normalizes the engine IPC `phase2.api_allowlist` trace into a top-level `api_allowlist` response object.
- The route fails closed as `contract_violation_blocked` when the allowlist is missing, not accepted, has the wrong `contract_id`, wrong `source_version`, wrong read/paper-write/denied action counts, records IBKR contact, serializes secret content, or fails to prove Bybit live execution protection.
- IPC unavailable still remains the existing degraded/fail-closed state rather than being reclassified as an IPC payload contract violation.
- Integer contract fields now reject boolean values, so `source_version=True` cannot satisfy `source_version=1`.

## Boundary

- This is a GET-only API normalization/readiness checkpoint.
- No IBKR contact, healthcheck, socket, connector construction, secret read/create/serialization, paper order, fill import, audit writer, DB apply, GUI authority, release, Phase 2 start, tiny-live, or live authority was added or exercised.
- No Bybit live execution behavior was changed.
- Linux `trade-core` runtime checkout was not touched or fast-forwarded.

## Verification

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py`
  - passed
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`
  - `12 passed`

## Dispatch Note

Sub-agent E2 was not spawned because the available sub-agent tool policy allows spawning only when the user explicitly asks for sub-agents or parallel agent work. This checkpoint is narrow and source-only; local diff review plus focused FastAPI/no-write tests covered the regression surface.

## Next Gate

Continue Phase 1 source-fixture/readiness hardening. Do not proceed to Phase 2 IBKR read-only contact until the immutable external-surface PASS artifact and real secret/topology evidence exist.
