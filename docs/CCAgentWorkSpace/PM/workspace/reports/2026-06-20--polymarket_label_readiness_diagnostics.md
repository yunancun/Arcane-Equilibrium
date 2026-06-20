# Polymarket Label-Readiness Diagnostics

Date: 2026-06-20
Owner: PM
Scope: artifact-only diagnostic upgrade for Polymarket lead-lag IC loop

## Summary

The Polymarket lead-lag lane is now producing real v2 probability deltas, but the current joined IC sample is still zero because forward-return labels have not matured yet.

This patch makes that distinction machine-readable:

- `polymarket_leadlag` report schema/runner bumped to v0.2.
- Reports now include `counts.label_readiness`.
- Cron status JSONL includes compact label-readiness fields.
- Alpha-discovery raw detail exposes the same fields for `polymarket_leadlag_ic`.

Result: the killboard can distinguish "keep capturing until labels mature" from "collector broken" or "price source broken".

## Runtime Evidence

Manual Linux smoke after the 12:07 UTC Polymarket collector:

- Artifact: `/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_20260620T121515Z.json`
- Latest: `/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_latest.json`
- sha256: `43f189ca875ecdb3dddded925e936eda51b98fe5a5396b1e75d7b86452ee1b8a`

Key fields:

- `schema_version=polymarket.leadlag_report.v0.2`
- `runner_version=polymarket_leadlag.v0.2`
- `snapshot_distinct_timestamps=2`
- `delta_rows=397`
- `feature_points=6`
- `joined_rows=0`
- `label_feature_horizon_pairs=18`
- `label_joinable_pairs=0`
- `label_status_counts={"exit_target_after_latest_price": 18}`
- `oldest_unmatured_exit_target_utc=2026-06-20T12:22:01.564000+00:00`

Alpha-discovery refresh:

- Created at: `2026-06-20T12:15:29Z`
- `polymarket_leadlag_ic` action: `RUN_READ_ONLY_CAPTURE`
- `sample_count=0`
- `ready_for_probe=0`
- `ready_for_aeg_chain=0`
- Raw detail preserves the same `label_status_counts`.

## Interpretation

The collector is not the current blocker:

- The 12:07 hourly collector produced a second v2 timestamp.
- The IC harness produced 397 probability deltas.
- Six feature cells exist across bucket/symbol combinations.

The current blocker is label maturity:

- The first forward-return target is around `2026-06-20T12:22:01Z`.
- At the 12:15 smoke, every feature×horizon pair needed a price at or after a future target timestamp.
- The correct action is still read-only capture, not promotion and not emergency debugging.

## Verification

Local:

```bash
PYTHONPATH=helper_scripts/research python3 -m pytest -q --import-mode=importlib helper_scripts/research/tests/test_polymarket_leadlag.py helper_scripts/research/tests/test_alpha_discovery_throughput.py
python3 -m pytest -q helper_scripts/cron/tests/test_polymarket_leadlag_ic_cron_static.py
bash -n helper_scripts/cron/polymarket_leadlag_ic_cron.sh
python3 -m py_compile helper_scripts/research/polymarket_leadlag/__init__.py helper_scripts/research/polymarket_leadlag/harness.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py
```

Results:

- `24 passed`
- `9 passed`
- bash syntax passed
- py_compile passed
- diff-check passed

Linux after selective source sync:

- `24 passed`
- `9 passed`
- bash syntax passed
- py_compile passed
- wrapper smoke passed
- alpha-discovery refresh passed

## Boundary

Allowed effects:

- Source/test/docs changes.
- Selective Linux source sync.
- `/tmp/openclaw` Polymarket IC artifact/status/log writes.
- Read-only PG `market.klines` SELECT path.

Explicit non-effects:

- No PG table write or schema migration.
- No Bybit private/signed/trading call.
- No engine/API rebuild or restart.
- No credential/auth/risk/order/strategy mutation.
- No signal output.
- No promotion proof.

## Next Trigger

Let the hourly IC cron run after labels mature. Expected progression:

- After 15m labels mature, `label_joinable_pairs` should become nonzero.
- Later hourly runs should fill 60m labels.
- 240m labels will lag by at least four hours.

Only after enough per-cell IC points clear `min_points=30` should the chain move to residual/regime/HAC/multiple-testing review.
