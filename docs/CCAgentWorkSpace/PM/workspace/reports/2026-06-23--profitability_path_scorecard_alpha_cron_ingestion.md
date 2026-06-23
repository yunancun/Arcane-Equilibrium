# PM Report: Profitability Path Scorecard Alpha-Cron Ingestion

Date: 2026-06-23

## Purpose

Close the gap between "we have many blockers" and "the autonomous loop knows the concrete path to profitability." The objective is not to lower the global Cost Gate or submit orders. The objective is to make the profit-closure ladder continuously refreshed and visible in alpha discovery: edge amplification, side-cell/horizon selection, bounded Demo proof, matched controls, and execution-realism gates.

## Changes

- `helper_scripts/cron/alpha_discovery_throughput_cron.sh` now refreshes `alpha_discovery_throughput/profitability_path_scorecard_latest.{json,md}` before running the runtime killboard.
- The scorecard refresh consumes existing local artifacts when present: Cost Gate counterfactual, profit-learning decision packet, learning plan, activation preflight, sealed replay/evidence, sealed probe preflight, bounded shadow/result/execution-realism reviews, MM fill-sim, Polymarket lead-lag, and Gate-B watch.
- Empty or missing inputs fail soft and still emit `alpha_profitability_path_scorecard_v1`.
- `runtime_runner.py` ingests the scorecard into the Cost Gate arm and mirrors compact closure fields at killboard top-level.
- `discovery_loop.py` and `learning_worklist.py` pass compact profitability closure evidence into blocker/worklist rows.

## Runtime Evidence

Linux canonical alpha cron smoke exited `0` after source sync to `497fe482`.

Latest scorecard:

- Generated: `2026-06-23T11:56:12.630119+00:00`
- Status: `PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING`
- Closure: `COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_OPERATOR_REVIEW`
- Leading path: `horizon_edge_amplification:ma_crossover|BTCUSDT|Sell`
- Leading candidate: `ma_crossover|BTCUSDT|Sell`
- Path count: `7`
- Cost Gate crossing candidates: `3`
- Remaining proof gates: `1`
- Required gate: operator records sealed-horizon review without granting order/probe authority

Boundary answers remained false: no global Cost Gate lowering, no order authority, no probe authority, no promotion proof.

## Verification

- Mac py_compile passed.
- Mac bash syntax passed.
- Mac focused alpha/worklist/cron suite: `72 passed`.
- Mac empty-input cron smoke passed and produced `NO_PROFITABILITY_PATH_ARTIFACTS`.
- Mac `git diff --check` passed.
- Linux py_compile passed.
- Linux bash syntax passed.
- Linux same focused suite: `72 passed`.
- Linux canonical alpha cron smoke passed.

No CI was run.

## Profitability Read

The system now continuously answers "how can we profit?" as a machine-readable artifact. The current best closure path remains side-cell/horizon edge amplification for `ma_crossover|BTCUSDT|Sell`, then a bounded Demo learning path after sealed-horizon operator review. In parallel, MM and Polymarket remain active learning routes for finding stronger low-friction or external-event alpha.

This does not prove profitability. It makes the proof ladder explicit and refreshed, so the autonomous loop can learn instead of waiting on one-off reports.

## Boundary

Source/test/docs plus artifact-only Mac/Linux smokes. No PG write/schema migration, no Bybit private/signed/trading call, no deploy/rebuild/restart, no crontab install, no env/auth/risk/order/strategy mutation, no global Cost Gate lowering, no active probe/order authority, no actual order, and no promotion proof.
