# REF-21 Replay Quality Upgrade

## Scope

This closes the quality pass after the full-chain replay runtime smoke. Replay
ownership remains unchanged: strategy/risk execution stays inside the dedicated
Rust `replay_runner` subprocess. Python continues to prepare fixtures,
register manifests, collect public-data recorder inputs, and spawn the existing
runner path.

## Implemented

- Added a recurring V058 symbol-universe recorder wrapper:
  `helper_scripts/cron/ref21_symbol_universe_snapshot_cron.sh`.
  - Writes only `market.symbol_universe_snapshots`.
  - Explicitly skips `governance.strategy_freeze_log` and V059 edge snapshots,
    because those are strategy/config freeze surfaces rather than hourly
    universe heartbeats.
  - Uses a local lock and touches
    `/tmp/openclaw/ref21_symbol_universe_snapshot_last_run`.
- Added a replay-specific public microstructure recorder:
  `helper_scripts/cron/ref21_market_microstructure_recorder.py`.
  - Uses the dedicated `ReplayBybitPublicClient`.
  - Records current ticker BBO rows into `market.market_tickers`.
  - Records L5 order-book summaries into `market.ob_snapshots`.
  - Uses a local process lock and never writes `trading.*`, `learning.*`,
    settings files, or governance state.
- Extended `ReplayBybitPublicClient` with allowlisted current ticker and
  orderbook endpoints plus separate conservative rate buckets.
- Added local microstructure overlay in `POST /api/v1/replay/full-chain/run`.
  - Fixture enrichment reads only locally recorded `market.market_tickers`
    rows.
  - Matching uses the latest prior BBO row with bounded staleness; future BBO
    rows are never used.
  - Overlay coverage and status are written into the fixture manifest and API
    response.
  - If local microstructure data is missing, the run still works but remains
    explicitly labeled as missing/empty coverage.
- Extended Rust replay fixture events with optional `best_bid`, `best_ask`,
  `bid_size`, `ask_size`, `spread_bps`, and `microstructure_source`.
- Updated Rust scanner timeline and tick context to consume fixture BBO when
  present, while keeping the existing synthetic fallback for legacy fixtures.
- Added passive healthcheck `[53] ref21_v058_symbol_universe_recorder` so a
  stopped V058 recorder surfaces as WARN/FAIL instead of silently causing
  survivorship-bias drift.

## Verification

- `bash -n helper_scripts/cron/ref21_symbol_universe_snapshot_cron.sh`
- `python3 -m py_compile helper_scripts/cron/ref21_market_microstructure_recorder.py program_code/exchange_connectors/bybit_connector/control_api_v1/replay/bybit_public_client.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_quick_routes.py`
- `python3 -m pytest tests/helper_scripts/test_ref21_backfill_v058_v059.py helper_scripts/cron/test_ref21_market_microstructure_recorder.py helper_scripts/db/test_replay_maintenance_healthchecks.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_bybit_public_client.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py -q`
  - 59 passed.
- `cargo test -p openclaw_engine scanner_timeline --features replay_isolated --manifest-path rust/Cargo.toml`
  - 5 passed.
- `cargo test -p openclaw_engine load_fixture_accepts_optional_turnover --features replay_isolated --manifest-path rust/Cargo.toml`
  - 1 passed.
- `cargo check -p openclaw_engine --bin replay_runner --features replay_isolated --manifest-path rust/Cargo.toml`
  - passed with pre-existing warnings.

## Reality Boundary

Bybit public REST ticker/orderbook endpoints are current snapshots, not
historical endpoints. This implementation does not fabricate historical L2
order books for windows before the local recorder existed. It improves future
replay fidelity by recording ticker/orderbook snapshots now, and it uses
existing local `market.market_tickers` history when available. Older windows
without local microstructure rows remain S2/S2+ public kline replay and are
explicitly labeled with missing microstructure coverage.
