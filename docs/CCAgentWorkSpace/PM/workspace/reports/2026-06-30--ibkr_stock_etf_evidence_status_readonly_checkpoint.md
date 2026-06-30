# 2026-06-30 IBKR Stock/ETF Evidence Status Read-Only Checkpoint

VERDICT: PASS
CONFIDENCE: high

## Result

- Added Rust IPC read-only fixture `stock_etf.get_evidence_status`, registered it in the Stock/ETF method registry, and routed it through the Stock/ETF IPC handler.
- The fixture returns a blocked `phase3_evidence_status_source_fixture` assembled from the existing market-data provenance and evidence-clock contracts: market-data provenance, evidence clock, frozen inputs, DQ manifest, scorecard, and Phase 2 gate context.
- Added authenticated no-store `GET /api/v1/stock-etf/evidence-status` in FastAPI. The route calls only `stock_etf.get_evidence_status` with empty params, ignores query/header state, fail-closes on IPC errors, and blocks contract violations.
- Updated `tab-stock-etf.html` to consume the new read-only endpoint and render an Evidence Status panel without adding write controls, browser storage authority, or direct broker APIs.

## Boundary

- This is a source-only Phase 4 display/readiness checkpoint; Phase 3 evidence collection was not started.
- No IBKR contact, healthcheck, socket, connector construction/runtime, secret read/create/serialization, evidence clock runtime, scorecard writer, DB apply, paper order, fill import, GUI authority, lane selector authority, release, tiny-live, or live authority was added or exercised.
- The API and GUI keep top-level runtime/authority fields false even when a malformed source payload reports side effects; those signals are surfaced only as contract violations.
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

Sub-agent E2 was not spawned because the available sub-agent tool policy allows spawning only when the user explicitly asks for sub-agents or parallel agent work. This checkpoint is cross-layer but still narrow and source-only; focused Rust IPC, FastAPI, static guard, and inline-script checks cover the regression surface.

## Next Gate

Continue Phase 4 display-only Stock/ETF views or source-contract hardening. Do not proceed to Phase 2 IBKR read-only contact, Phase 3 evidence collection, connector runtime, or paper-order authority until the immutable external-surface PASS artifact and real secret/topology evidence exist.
