# REF-21 V058/V059 API Driver Checkpoint

## Scope

This checkpoint closes the Control API source-driver gap for the one-click
full-chain replay run path. It does not change replay execution ownership:
strategy/risk still run only in the dedicated Rust `replay_runner` subprocess.

## Implemented

- `POST /api/v1/replay/full-chain/run` now passes the selected strategy list
  into fixture preparation so historical edge snapshots can be scoped before
  manifest registration.
- For `universe_preset=current_scanner`, the run path first reads V058
  `market.symbol_universe_snapshots` for symbols active during the requested
  window. If V058 is unavailable or empty, it emits
  `historical_universe_unavailable_fell_back_to_current_scanner:*` and falls
  back to the legacy current-scanner path.
- The run path reads V059 `learning.edge_estimate_snapshots` at
  `asof_ts <= data_window_start`, filters deprecated rows, normalizes payloads
  into Rust `EdgeEstimates` JSON cells, and embeds them into V049
  `manifest_jsonb.edge_estimates`.
- The response and manifest now expose `universe_source`,
  `historical_universe`, and `edge_snapshot_meta` for operator audit.
- Replay UI copy now labels the default universe option as
  `Historical universe (V058)`.

## Remaining

- V058/V059 migrations were previously dry-run with rollback proof; Linux
  production still needs persistent apply/backfill before the default path can
  avoid fallback in real operation.
- V059 has no writer/backfill in this checkpoint; missing cells produce an
  explicit `edge_snapshot_unavailable:*` warning and an empty edge snapshot.
- Runner scanner ticker reconstruction remains OHLCV-derived. Historical
  order-book/ticker fidelity is still a separate data-realism upgrade.

## Verification

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py -q`
