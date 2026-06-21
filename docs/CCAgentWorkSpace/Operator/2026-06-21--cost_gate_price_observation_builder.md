# Cost-Gate Price Observation Builder

## Status

Implemented source-only support for building local price observation artifacts from the cost-gate learning ledger.

No deploy, restart, DB write, or Bybit call was performed.

## What Changed

- Added `price_observations.py` under the cost-gate demo-learning lane.
- It reads `probe_ledger.jsonl` and finds admission rows that still need market outcomes.
- It builds required price windows and filters local price/kline rows into normalized observations.
- Output can be JSON with metadata or JSONL rows directly consumable by `runtime_adapter --price-observations`.
- Alpha-discovery now tells us to build price observations before recording blocked-signal outcomes.

## Important Boundary

This is learning infrastructure only.

- It does not lower the main Cost Gate.
- It does not submit demo or live orders.
- It does not grant order authority.
- It does not write PG.
- It does not call Bybit.
- It does not change runtime config, risk, auth, or strategy state.

## Verification

- Cost-gate learning lane tests: 18 passed.
- Alpha-discovery focused tests: 34 passed.
- Python compile: passed.
- CLI help smoke: passed.
- `git diff --check`: passed.

## Operator Next Step

Once runtime ledger rows exist, provide or generate a local price/kline export, build observations with `price_observations.py`, then run `runtime_adapter --record-blocked-outcomes`. Review whether blocked signals were actually profitable before considering any side-cell demo probe authority.
