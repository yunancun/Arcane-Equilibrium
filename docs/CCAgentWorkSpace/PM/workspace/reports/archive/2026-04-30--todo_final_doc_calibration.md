# TODO Final Doc Calibration

Date: 2026-04-30
Owner: PM

## Scope

Operator requested the final TODO/doc calibration and push.

This was a documentation-only pass. No code, DB write, runtime config, rebuild, restart, live authorization, or strategy/risk parameter action was performed.

## Calibrated Facts

- Doc-calibration baseline before this docs-only commit: Mac source HEAD `5584785`, clean.
- Doc-calibration baseline before this docs-only commit: Linux source HEAD `5584785`, clean.
- Code-bearing runtime checkpoint remains `a9fce24` because the source cleanup and this doc pass were not rebuilt/restarted.
- Linux watchdog was fresh: demo/live alive, paper inactive by design.
- Latest cron-wrapper healthcheck at 2026-04-30 23:11 CEST returned SUMMARY WARN, exit 0.

Current healthcheck WARNs:

- `[4]` phys_lock_runtime.
- `[11]` counterfactual replay JSON age 17.2h; sample count already 864/200.
- `[33]` maker_fill_rate: rolling 7d fee_drop 20.8%, maker_like 25.6%.
- `[38]` grid_trading_lifecycle_drift.
- `[40]` realized_edge_acceptance.

Current important PASSes:

- `[13]` edge scheduler fresh.
- `[14]` exit_features accumulation: grid and ma_crossover READY.
- `[35]` learning data contract.
- `[36]` advisory/live lease boundary.
- `[37]` demo applier audit/live boundary.
- `[39]` strategy name cardinality.

## TODO Changes

- Updated the runtime/source snapshot from stale `d847fb8` wording to the docs-only baseline `5584785`, while making clear this doc commit is not a runtime-bearing checkpoint and runtime remains `a9fce24`.
- Updated healthcheck ground truth to the cron-wrapper `[1]`-`[40]` output and removed reliance on old `[0]` mappings.
- Recalibrated stale G5 line-count rows:
  - `main.rs` is 1162 LOC.
  - `instrument_info.rs` is 1008 LOC.
  - `bybit_rest_client.rs`, `order_manager.rs`, `startup/mod.rs`, `paper_state/resting_orders.rs`, and `config/risk_config.rs` are all below 1200.
- Closed stale G3-08 warning-zone rows:
  - `analyst_agent.py` is 764 LOC.
  - `h_state_query_handler.py` is 452 LOC.
  - `strategist_agent.py` is 797 LOC.
  - MAF lazy PEP 562 re-export remains accepted; `SCOUT_AGENT` is already registered in `CLAUDE.md`.
- Reframed remaining size work as a separate high-risk wave:
  - `rust/openclaw_engine/src/bybit_private_ws.rs` 1413 LOC.
  - `rust/openclaw_engine/src/tick_pipeline/commands.rs` 1343 LOC.
  - large Rust/Python test files.

## Verification

- `git status --short --branch`: clean before edits, then reviewed after docs changes.
- Linux source/watchdog verified over SSH.
- Latest Linux healthcheck log read from `/tmp/openclaw/passive_wait_healthcheck_cron.log`.
- `wc -l` used to verify current line-count claims.
- Grep spot-check used to find remaining stale active strings; remaining hits are historical rows or this report's own before/after description.
- `git diff --check` passed.
