# REF-21 C2 Recorder Coverage Preflight Checkpoint

## Scope

This checkpoint adds a read-only recorder coverage preflight before one-click
full-chain replay. It does not fetch Bybit public market data, does not spawn
`replay_runner`, and does not read or mutate strategy/risk settings.

## Implemented

- Added `app/replay_data_coverage.py`.
  - Estimates replay-window coverage from local recorder tables:
    `market.market_tickers`, `market.ob_snapshots`, and
    `market.symbol_universe_snapshots`.
  - Reports BBO, funding rate, open interest, index price, orderbook depth,
    and tick-size coverage.
  - Produces tiered verdicts:
    `S2_PUBLIC_KLINE_ONLY`, `S2_PLUS_LOCAL_BBO`, `S1_LIMITED_READY`,
    `S1_CALIBRATED_READY`.
- Added `POST /api/v1/replay/full-chain/coverage`.
  - Auth-gated with the same replay write/operator path and rate limiter as
    full-chain run.
  - Resolves the replay universe, edge snapshot status, recorder coverage, and
    execution calibration samples.
  - Returns `execution_mode=read_only_preflight_no_subprocess` and
    `promotion_allowed=false`.
- Updated one-click Replay GUI.
  - Runs coverage preflight first.
  - Shows BBO, orderbook, funding, OI, tick-size, edge snapshot, and execution
    sample verdicts before launching the real replay run.

## Verification

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_data_coverage.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_replay_subtab_static_assets.py -q`
  - 55 passed.
- `git diff --check`

## Boundary

The preflight estimates whether local recorder data exists for the selected
window. It does not fabricate missing BBO/orderbook history. Old windows remain
S2/S2+ unless recorder coverage and execution samples actually satisfy the
thresholds.
