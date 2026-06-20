# 2026-06-20 Polymarket Lead-Lag IC Harness

## Summary

Added a fail-closed, artifact-only harness for the active Polymarket v2 hourly data lane:

- Source: `helper_scripts/research/polymarket_leadlag/`
- Test: `helper_scripts/research/tests/test_polymarket_leadlag.py`
- Runtime latest: `/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_latest.json`

The harness now answers the next profit-search question mechanically: do Polymarket event/regulatory odds changes lead Bybit perp returns after leak-free timestamp alignment?

## Method

- Load Polymarket point-in-time `polymarket_axis_runs` snapshots for a selected query set and mode.
- Compute `Yes` implied-probability delta from previous snapshot to current snapshot per market.
- Bucket rows in the research harness, not the collector:
  - `price_target`
  - `event_reg`
  - `other`
- Infer BTC/ETH/SOL/XRP perp symbols from market question/title/discovery query text.
- Join Bybit forward returns from `market.klines` using first kline at/after snapshot and first kline at/after `t+h`.
- Emit statuses that fail closed:
  - `NO_SNAPSHOT_ROWS`
  - `NO_PRICE_DATA`
  - `INSUFFICIENT_SAMPLE`
  - `IC_READY_NO_SIGNIFICANT_EDGE`
  - `IC_CANDIDATE_REVIEW_REQUIRED`

Promotion boundary remains `research_context_only_not_signal_or_promotion_proof`.

## Runtime Smoke

Linux `trade-core` smoke used current v2 hourly artifacts and read-only PG price data:

```text
status=INSUFFICIENT_SAMPLE
reason=max joined IC points 0 below min_points 20
snapshot_rows=860
snapshot_distinct_timestamps=1
price_rows=32
delta_rows=0
joined_rows=0
query_set_version=v2
price_source=pg:market.klines:1m
```

Artifact:

```text
/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_20260620T114427Z.json
```

This is the correct verdict: there is only one v2 hourly timestamp, so no probability deltas can exist yet.

## Verification

Local:

```text
PYTHONPATH=helper_scripts/research python3 -m pytest -q --import-mode=importlib helper_scripts/research/tests/test_polymarket_leadlag.py
4 passed

python3 -m py_compile helper_scripts/research/polymarket_leadlag/__init__.py helper_scripts/research/polymarket_leadlag/harness.py
PASS

git diff --check -- helper_scripts/research/polymarket_leadlag helper_scripts/research/tests/test_polymarket_leadlag.py
PASS
```

Linux:

```text
PYTHONPATH=helper_scripts/research python3 -m pytest -q --import-mode=importlib helper_scripts/research/tests/test_polymarket_leadlag.py
4 passed

python3 -m py_compile helper_scripts/research/polymarket_leadlag/__init__.py helper_scripts/research/polymarket_leadlag/harness.py
PASS
```

## Boundaries

- PG path uses readonly session plus SELECT `market.klines`.
- Runtime smoke also set `PGOPTIONS="-c default_transaction_read_only=on"`.
- Writes are limited to `/tmp/openclaw/research/polymarket_leadlag/` artifact files.
- No PG table write or schema migration.
- No Bybit private/signed/trading call.
- No engine/API rebuild or restart.
- No credential/auth/risk/order/strategy mutation.
- Not promotion proof.

## Next Trigger

Let active hourly v2 collection accumulate at least 20-30 distinct hourly timestamps, then rerun the same harness. Any `IC_CANDIDATE_REVIEW_REQUIRED` result is only a review input and still needs residualization, regime slicing, HAC/serial-dependence handling, and multiple-testing control before QC/MIT/AI-E can treat it as an alpha candidate.
