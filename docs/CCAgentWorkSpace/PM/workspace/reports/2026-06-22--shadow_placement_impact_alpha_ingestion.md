# Shadow Placement Impact Alpha Ingestion

Date: 2026-06-22
Source commit: `f0d422b2`

## Summary

v418 wires the existing `bounded_demo_probe_shadow_placement_impact_v1` artifact into the main autonomous alpha/worklist/profitability loop.

This does not lower Cost Gate and does not grant probe/order authority. It turns the v417 mechanical touchability evidence into a first-class repair task so the system stops treating it as a standalone report.

## Engineering Change

- `runtime_runner.py` now emits `alpha_discovery_runtime_killboard_v9` and ingests `bounded_probe_shadow_placement_impact_latest.json`.
- `discovery_loop.py` now keeps bounded result-review/execution-realism evidence ahead of shadow placement evidence, then lets shadow placement supersede the older blocked-review route when no result-review decision exists.
- `learning_worklist.py` now emits `alpha_learning_worklist_v6` and task type `bounded_probe_placement_repair`.
- `profitability_path_scorecard.py` now accepts `--bounded-probe-shadow-placement-impact-json` and carries shadow placement status/sample/touchability fields into path evidence, closure, answers, and artifact summaries.

## PM Read

The current blocker is no longer "we measured shadow impact but the learning loop does not consume it." The blocker is now explicit: operator review of the near-touch repair, then candidate-matched order-to-fill and fill-backed lineage after separate authorization.

The current shadow sample still has `candidate_matched_order_count=0`, so it is mechanical touchability evidence, not `ma_crossover|BTCUSDT|Sell` alpha proof. Actual bounded result-review evidence remains higher priority than the shadow artifact.

## Verification

- Mac py_compile passed.
- Mac focused shadow ingestion tests: `2 passed`.
- Mac related alpha/worklist/scorecard + bounded-probe suite: `107 passed`.
- `git diff --check` passed before source commit.
- Source commit `f0d422b2` pushed with `[skip ci]`.
- Linux source fast-forwarded clean to `f0d422b2`.
- Linux py_compile passed.
- Linux same related suite: `107 passed`.
- No CI run.

## Boundary

Source/test/docs + Linux source sync/read-only/static tests only. No PG write/schema migration, no Bybit private/signed/trading call, no deploy/rebuild/restart, no crontab install/env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, and no promotion proof.
