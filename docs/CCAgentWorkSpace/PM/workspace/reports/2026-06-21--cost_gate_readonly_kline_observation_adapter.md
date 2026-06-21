# Cost-Gate Read-Only Kline Observation Adapter

## PM Verdict

Implemented the next learning-loop increment: `price_observations.py` can now source observation rows directly from local read-only PG `market.klines`.

This is still artifact-only. It does not write PG, does not touch runtime config, and does not grant Cost Gate or order authority.

## Why This Matters

v313 made the Module deep enough to derive observation windows from the cost-gate ledger, but it still required a hand-built price/kline export. That left the feedback loop partly manual.

v314 adds the second Adapter behind the same Interface:

- `--source-prices`: local JSON/JSONL price export
- `--source-pg`: read-only local `market.klines` SELECT

The output remains the same `windows` + normalized `observations` artifact that `runtime_adapter --record-blocked-outcomes` already consumes.

## Changed

- Added `--source-pg` CLI mode to `helper_scripts/research/cost_gate_learning_lane/price_observations.py`.
- Reused `helper_scripts.lib.pg_connect.connect_report_pg`.
- After the helper sets statement timeout, the Adapter rolls back setup state and switches to `readonly=True, autocommit=True`.
- Added `build_market_klines_observation_sql()` and `fetch_market_kline_price_rows(...)`.
- The SQL reads only `market.klines`, grouped by ledger-derived symbol/time windows.
- Normalized observations preserve `source=pg_market_klines` and `timeframe`.
- Existing `--source-prices` behavior remains.

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` -> 19 passed.
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> 34 passed.
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/price_observations.py` -> passed.
- `PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.price_observations --help` -> passed.
- Empty-ledger `--source-pg --print-json` smoke -> passed without PG connection.
- `git diff --check` -> passed.

The focused test suite now asserts the PG SQL is read-only, references `market.klines`, uses UTC time params, and produces observations accepted by the existing builder.

## Boundary

- No PG table write or schema migration.
- PG path is SELECT-only and read-only when operator runs it.
- No Bybit private, signed, public, or trading call.
- No engine/API rebuild, restart, deploy, or runtime flag change.
- No credential, authorization, risk, order, strategy, or config mutation.
- Not signal proof, execution proof, promotion proof, or Cost Gate relaxation.

## Next

Once runtime ledger rows exist on Linux, run `price_observations.py --source-pg` against the ledger to generate the observation artifact, then run `runtime_adapter --record-blocked-outcomes`. The resulting blocked-signal markouts are the evidence needed before any side-cell-specific demo probe authority discussion.
