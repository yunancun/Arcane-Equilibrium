# 2026-06-30 IBKR Stock/ETF GUI Contract Endpoint Hardening Checkpoint

VERDICT: PASS
CONFIDENCE: high

## Result

- `gui_lane_contract_v1` now requires the actual Stock/ETF read-only GUI API surface: readiness, lane-status, and evidence-status.
- Added endpoint constants, GET-only fields, mismatch blockers, template fields, and acceptance coverage for the three display-only endpoints.
- The Phase 0 named contract packet now documents the three-endpoint GUI contract instead of readiness-only.

## Boundary

- Source-only contract/test/spec hardening.
- No IBKR contact, connector runtime, secret access, evidence clock runtime, scorecard writer, DB apply, paper order, fill import, GUI/lane selector authority, release, tiny-live, or live authority was added or exercised.
- Existing Python/static guards still prove the GUI is display-only and rejects write-capable surfaces.
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

Sub-agent E2 was not spawned because the available sub-agent tool policy allows spawning only when the user explicitly asks for sub-agents or parallel agent work. Focused GUI contract tests plus full `openclaw_types` and FastAPI/static guards covered this source-only read-surface contract change.

## Next Gate

Keep IBKR Stock/ETF in source-only/pre-contact mode. Do not initiate IBKR read-only contact, Phase 3 collector/evidence clock, connector runtime, DB apply, scorecard writing, or paper order authority until the required immutable gates and real secret/topology evidence exist.
