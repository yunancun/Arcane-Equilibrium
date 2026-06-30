# 2026-06-30 IBKR Stock/ETF GUI Contract Endpoint Hardening Checkpoint

VERDICT: PASS
CONFIDENCE: high

## Result

- Hardened `gui_lane_contract_v1` so the source contract now requires all three current Stock/ETF display-only GET surfaces: `/api/v1/stock-etf/readiness`, `/api/v1/stock-etf/lane-status`, and `/api/v1/stock-etf/evidence-status`.
- Added exact endpoint constants and GET-only fields for lane-status and evidence-status, with blockers for endpoint mismatch or non-GET contract claims.
- Updated the blocked GUI lane template and Phase 0 named contract packet to match the current three-endpoint read-only surface.
- Updated acceptance tests so accepted fixtures prove all three endpoints and malformed endpoint paths/query strings fail closed.

## Boundary

- This is a source-only GUI contract/test/spec hardening checkpoint.
- No IBKR contact, healthcheck, socket, connector construction/runtime, secret read/create/serialization, evidence clock runtime, scorecard writer, DB apply, paper order, fill import, GUI authority, lane selector authority, release, tiny-live, or live authority was added or exercised.
- The static GUI remains display-only and the existing FastAPI/static guards still reject write methods, direct `fetch`, forms, browser storage lane authority, direct IBKR broker writes, and Stock/ETF write IPC strings.
- No Bybit live execution behavior was changed.
- Linux `trade-core` runtime checkout was not touched or fast-forwarded.

## Verification

- `rustfmt --edition 2021 rust/openclaw_types/src/stock_etf_gui_lane_contract.rs rust/openclaw_types/tests/stock_etf_gui_lane_contract_acceptance.rs`
  - passed
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_gui_lane_contract_acceptance`
  - `9 passed`
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_phase0_manifest_acceptance`
  - `6 passed`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`
  - `27 passed`
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`
  - `35` unit/golden tests + `182` integration/acceptance tests + `0` doc-tests passed
- `git diff --check`
  - passed

## Dispatch Note

Sub-agent E2 was not spawned because the available sub-agent tool policy allows spawning only when the user explicitly asks for sub-agents or parallel agent work. This checkpoint is narrow and source-only; focused GUI contract tests plus full `openclaw_types` and FastAPI/static guards cover the regression surface.

## Next Gate

Continue source-only contract hardening or Phase 4 display-only views. Do not proceed to Phase 2 IBKR read-only contact, Phase 3 collector/evidence-clock runtime, connector runtime, DB apply, or paper-order authority until the required immutable gates and real secret/topology evidence exist.
