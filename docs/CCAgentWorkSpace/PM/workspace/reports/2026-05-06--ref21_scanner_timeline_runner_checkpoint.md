# REF-21 Scanner Timeline Runner Checkpoint

## Scope

This checkpoint moves REF-21 full-chain replay from a static scanner-universe
snapshot toward a replayed scanner timeline inside the dedicated Rust
`replay_runner` subprocess.

## Implemented

- Added `rust/openclaw_engine/src/replay/scanner_timeline.rs`.
- Reconstructs scanner scan cycles from replay fixture OHLCV rows.
- Reuses scanner pure scoring, market judgement, opportunity scoring,
  correlation filtering, and `SymbolRegistry` anti-churn logic.
- Uses REF-21 replay defaults: 60-second scan interval and zero warmup when
  no scanner config snapshot is supplied.
- `replay_runner` now reads `manifest.mode == "full_chain"` and builds the
  scanner timeline before executing strategy/risk adapters.
- Adapter-path runner now gates strategy ticks by historical scanner active
  symbols, while still allowing already-open positions to receive ticks for
  exits.
- Runner diagnostics now include `scanner_timeline_enabled`,
  `scanner_timeline_cycles`, and `scanner_timeline_skipped_events`.
- V049 runtime manifest payload propagation now preserves `mode`,
  `scanner_config`, and `edge_estimates` so the signed manifest reaching Rust
  does not lose REF-21 fields.
- Replay tab copy now says `historical scanner timeline`; Advanced workflow is
  unchanged.

## Remaining

- The current one-click API still builds the initial fixture symbol list from
  request/current scanner/custom universe. V058 `market.symbol_universe_snapshots`
  is not yet queried as the default historical universe source.
- V059 edge snapshots are supported by the Rust manifest path when supplied,
  but the Control API does not yet query and embed them by default.
- The runner still uses fixture OHLCV-derived 24h ticker approximations; this is
  replay-safe and deterministic, but it is not a historical Bybit ticker/order
  book reconstruction.

## Verification

- `node --check program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/app-paper.js`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_replay_subtab_static_assets.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_bybit_public_client.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_route_helpers_fixture_default_env.py -q`
- `cargo check --bin replay_runner --features replay_isolated`
- `cargo test scanner_timeline --features replay_isolated`
- `cargo test adapter_pipeline_scanner_timeline_gates_inactive_entries --features replay_isolated`

