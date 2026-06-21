# Cost-Gate Read-Only Kline Observation Adapter

## Status

Implemented source-only support for reading local `market.klines` as the price source for cost-gate learning-lane observations.

No deploy, restart, DB write, schema change, or Bybit call was performed.

## What Changed

- `price_observations.py` now supports `--source-pg`.
- It reads only local PG `market.klines` for the symbol/time windows derived from `probe_ledger.jsonl`.
- It keeps the same output artifact used by `runtime_adapter --record-blocked-outcomes`.
- The previous local file mode remains available as `--source-prices`.

## Important Boundary

This is evidence plumbing only.

- It does not lower the main Cost Gate.
- It does not submit demo or live orders.
- It does not grant order authority.
- It does not write PG.
- It does not call Bybit.
- It does not change runtime config, risk, auth, or strategy state.

## Verification

- Cost-gate learning lane tests: 19 passed.
- Alpha-discovery focused tests: 34 passed.
- Python compile: passed.
- CLI help smoke: passed.
- Empty-ledger `--source-pg` smoke: passed without PG connection.
- `git diff --check`: passed.

## Operator Next Step

After the runtime writer is enabled and ledger rows exist on Linux, run the observation builder with `--source-pg`, then run `runtime_adapter --record-blocked-outcomes`. Review blocked-signal net bps before considering any side-cell demo probe authority.
