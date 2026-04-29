# W1-T2 Attribution Gap Close

Date: 2026-04-29 21:20 CEST

## Result

W1-T2 producer-side attribution is now complete and deployed.

- Code commits: `5895579` + hotfix `854cae1`.
- Linux `trade-core`: HEAD `854cae1`, clean.
- Runtime: engine PID `779344`, API PID `779449`, watchdog healthy.
- No live/demo risk config change, no strategy shutdown, no live authorization relaxation.

## What Changed

- Close fills now write normalized `strategy_name` plus free-text `exit_reason`.
- Zero-PnL IPC/manual close rows with close prefixes now also write `exit_reason`.
- `[38]` grid lifecycle healthcheck now works across legacy and V033 row shapes.
- `[39]` cardinality drift now hard-fails on recent 1h regression and WARNs during 24h legacy-row rollover.
- Learning dashboard copy no longer implies shadow-only/no-order behavior where the engine mode is actually demo/live_demo execution.

## Current Runtime Signal

Passive healthcheck remains SUMMARY FAIL because `[38]` is a real behavior signal:

- live_demo grid re-entry rate: 0.72
- lifetime_ratio live_demo/demo: 0.35
- `[39]`: WARN only, 1h distinct strategy_name=7; 24h distinct=22 legacy rows aging out.

## Next Decision

This is now a grid risk-policy decision. Options remain: pause selected negative grid cells, widen live_demo trailing distance, reduce grid levels, or disable partial TP. Do not treat the remaining `[38]` FAIL as a deployment failure.
