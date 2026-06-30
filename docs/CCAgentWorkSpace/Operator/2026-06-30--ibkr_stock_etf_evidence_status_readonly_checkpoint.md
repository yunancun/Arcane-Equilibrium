# 2026-06-30 IBKR Stock/ETF Evidence Status Read-Only Checkpoint

VERDICT: PASS
CONFIDENCE: high

## Result

- `stock_etf.get_evidence_status` is now an explicit read-only Rust IPC fixture and registry method.
- FastAPI exposes authenticated `GET /api/v1/stock-etf/evidence-status` with no-store/private cache headers, empty IPC params, fail-closed normalization, and contract-violation handling for Phase 3, IBKR contact, secret, scorecard, DB, order, and Bybit IPC reuse side-effect signals.
- The Stock/ETF static tab now renders an Evidence Status panel from the read-only endpoint while preserving display-only GUI behavior.
- Route/static tests now require the evidence-status endpoint and still reject POST/PUT/PATCH/DELETE snippets, direct `fetch`, forms, browser storage lane authority, direct IBKR write APIs, and Stock/ETF write IPC strings.

## Boundary

- Phase 3 evidence collection was not started.
- No IBKR contact, healthcheck, socket, connector construction/runtime, secret read/create/serialization, evidence clock runtime, scorecard writer, DB apply, paper order, fill import, release, tiny-live, or live authority was added or exercised.
- No GUI/lane selector authority was added; paper order entry remains hidden.
- No Bybit live execution behavior was changed.
- Linux `trade-core` runtime checkout was not touched or fast-forwarded.

## Verification

- `rustfmt --edition 2021 rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs rust/openclaw_engine/src/ipc_server/method_registry.rs rust/openclaw_engine/src/ipc_server/dispatch.rs rust/openclaw_engine/src/ipc_server/tests/stock_etf.rs`
  - passed
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf`
  - `8 passed`
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`
  - passed
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`
  - `27 passed`
- Node inline script syntax check for `tab-stock-etf.html`
  - `checked 2 inline scripts`
- `git diff --check`
  - passed

## Dispatch Note

Sub-agent E2 was not spawned because the available sub-agent tool policy allows spawning only when the user explicitly asks for sub-agents or parallel agent work. Focused cross-layer checks cover this source-only read surface.

## Next Gate

Keep Stock/ETF IBKR in pre-contact display/source-fixture mode. Do not initiate IBKR read-only contact, Phase 3 evidence collection, connector runtime, scorecard writing, DB apply, or paper order authority until the required immutable gate and real secret/topology evidence exist.
