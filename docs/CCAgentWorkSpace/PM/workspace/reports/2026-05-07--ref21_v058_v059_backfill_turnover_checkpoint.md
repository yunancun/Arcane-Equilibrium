# REF-21 V058/V059 Backfill + Turnover Checkpoint

## Scope

This checkpoint continues P0-REF21-6b. It does not change replay ownership:
strategy/risk execution remains inside the dedicated Rust `replay_runner`
subprocess. Python changes are limited to fixture preparation/backfill helpers
and Bybit public-data parsing.

## Parallel Dispatch

- `MIT/E2-style DB investigation`: confirmed V058/V059 production tables existed
  but had zero rows; V060/V061 were still absent on Linux.
- `BB/Scanner data investigation`: confirmed Bybit kline row[6] already carries
  historical turnover and should be preserved instead of reconstructing turnover
  only as `close * volume`.
- `QA/E2E investigation`: confirmed one-click full-chain replay can run from
  public kline data once Linux has the release `replay_runner` binary rebuilt
  and API code synced.

## Implemented

- Added `helper_scripts/db/ref21_backfill_v058_v059.py`.
  - Default is dry-run.
  - `--apply` writes V058 `market.symbol_universe_snapshots`, V058
    `governance.strategy_freeze_log`, and V059
    `learning.edge_estimate_snapshots`.
  - Instrument universe source is Bybit public
    `bybit-public://v5/market/instruments-info?category=...`.
  - Default instrument statuses are `Trading,PreLaunch,Delivering,Closed`,
    fetched explicitly and de-duped by category/symbol.
  - Symbols outside the V058 schema contract, such as dated futures symbols
    with hyphens, are skipped instead of being written into the perp replay
    universe.
  - `--asof` controls the V058 snapshot timestamp; `--freeze-asof` separately
    controls the strategy freeze-log timestamp.
  - V059 source is the existing `settings/edge_estimates*.json` files.
- Added helper tests for instrument parsing and edge snapshot row generation.
- Preserved Bybit public kline `turnover` in replay fixtures.
- Extended Rust `MarketEvent` with optional `turnover`.
- Updated Rust scanner timeline ticker reconstruction to use fixture turnover
  when present and fall back to `close * volume` for legacy fixtures.

## Verification

- `python3 -m pytest tests/helper_scripts/test_ref21_backfill_v058_v059.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_bybit_public_client.py -q`
  - 10 passed.
- `python3 -m py_compile helper_scripts/db/ref21_backfill_v058_v059.py program_code/exchange_connectors/bybit_connector/control_api_v1/replay/bybit_public_client.py`
  - passed.
- `python3 helper_scripts/db/ref21_backfill_v058_v059.py --skip-instruments`
  - dry-run only; produced 1 freeze row and 1 edge snapshot row.
- `venvs/mac_dev/bin/python helper_scripts/db/ref21_backfill_v058_v059.py --skip-edge --skip-freeze-log --rps 2 --categories linear`
  - dry-run only; fetched 655 Trading, 1 PreLaunch, 0 Delivering, and 803
    Closed instruments; after V058 symbol-contract filtering, 905 universe
    rows remained.
- `cargo test scanner_timeline --features replay_isolated`
  - 4 passed.
- `cargo test load_fixture_accepts_optional_turnover --features replay_isolated`
  - 1 passed.
- `cargo check -p openclaw_engine --bin replay_runner --features replay_isolated`
  - passed with pre-existing warnings.

## Known Limitations

- Mac system Python 3.10 certificate trust failed when directly fetching Bybit
  instruments-info. The project `venvs/mac_dev` Python 3.12 succeeded; Linux
  `trade-core` remains the runtime verifier.
- This is still public kline + instrument metadata replay. It is not historical
  order-book replay.
- A one-shot current public instruments-info backfill cannot recover symbols
  already absent from Bybit public instruments-info; durable historical coverage
  still requires recurring V058 snapshots.
- V058/V059 production backfill and V060/V061 persistent migration apply still
  need to be run on Linux after source sync.

## Next Steps

1. Commit and push this checkpoint.
2. Pull on Linux `trade-core`.
3. Apply missing V060/V061 migrations if still absent.
4. Run V058/V059 backfill dry-run, then `--apply` if counts are sane.
5. Build release `replay_runner` with `--features replay_isolated`.
6. Restart/reload API so the Bybit public client turnover parser is active.
