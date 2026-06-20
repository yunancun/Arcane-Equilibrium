# MM Gross-Edge Near-Miss Ranking

Date: 2026-06-20

## Summary

The current MM blocker already says current fees require 4.0bp gross edge and the best sample-gated gross edge is only 2.27bp. This checkpoint adds the ranked near-miss list behind that diagnosis, so the next signal search can start from measured surfaces instead of a single best cell.

This is diagnostic-only. It does not change fill logic, fee assumptions, strategy parameters, order behavior, or promotion gates.

## Changes

- Added `top_sample_gated_gross_cells` to `recorder_mm_verdict_cron.sh` gross-edge decomposition.
- Passed the list through `mm_cost_wall_escape_v1` in alpha-discovery.
- Added static and alpha focused regression coverage.

## Runtime Evidence

Linux read-only smoke:

- MM verdict status timestamp: `2026-06-20T19:18:50Z`
- Latest alpha SHA256: `4dbbb4e964b1077f2b901a7d651b06c59d4cc3622c49b132e47b6b4f511c9583`
- Alpha created: `2026-06-20T19:19:00.916678+00:00`
- Global status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- `engineering_actionable_count`: 1

Top sample-gated gross-edge near misses:

- `LABUSDT` / edge_scorecard / back / informed_skip: gross 2.27bp, net -1.73bp, n=170
- `ADAUSDT` / walk_forward_holdout: gross 2.002bp, net -1.998bp, n=714
- `quoted_half_spread_bps_train_p90_ge` / walk_forward_holdout: gross 1.565bp, net -2.435bp, n=1208
- `ADAUSDT` / edge_scorecard / back / informed_skip: gross 1.459bp, net -2.541bp, n=911
- `ICPUSDT` / walk_forward_holdout: gross 1.386bp, net -2.614bp, n=249

Current required gross edge remains 4.0bp, so every measured near miss is still below the current-fee threshold.

## Interpretation

The current MM family is not random noise only; it has weak positive gross-edge pockets. The problem is magnitude and fee friction. The best measured pockets are still far enough below 4.0bp that further thresholding inside the same surface is unlikely to be the fastest path. A next MM research path should either materially reduce friction or introduce a new signal source that can push sample-gated gross edge above the current fee round trip.

## Verification

- Mac: `test_alpha_discovery_throughput.py` = 28 passed.
- Mac: `test_fill_sim_refresh_cron_static.py` = 11 passed.
- Mac: bash syntax for `recorder_mm_verdict_cron.sh` passed.
- Mac: py_compile for alpha discovery modules passed.
- Mac: `git diff --check` passed.
- Linux selective source sync: same focused suites = 28 passed + 11 passed.
- Linux bash syntax and py_compile passed.
- Linux read-only MM verdict cron + alpha-discovery cron smoke refreshed the evidence above.

## Boundary

Source/test/docs plus selective Linux source sync and `/tmp/openclaw` artifact writes only. No PG table write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart, no credential/auth/risk/order/trading mutation, and no live/demo strategy parameter change.

This is not promotion proof and not a trading signal.
