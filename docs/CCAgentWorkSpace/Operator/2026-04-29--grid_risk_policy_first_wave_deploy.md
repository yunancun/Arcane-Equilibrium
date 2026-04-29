# Grid Risk Policy First Wave Deploy

Date: 2026-04-29 21:44 UTC

## Applied

Commit `6fdcc91` applied the approved RFC first wave:

- `settings/strategy_params_live.toml`
- `grid_trading.grid_levels`: `10` → `7`
- Added demo robust-negative `blocked_symbols` to live/live_demo:
  `BSBUSDT`, `PRLUSDT`, `ZBTUSDT`, `FARTCOINUSDT`, `SOLUSDT`, `DOGEUSDT`, `GALAUSDT`, `ENAUSDT`, `AAVEUSDT`, `ORCAUSDT`, `PENGUUSDT`

Boundary: this only blocks new grid entries on listed symbols. Existing positions can still close/reduce normally. No trailing, partial TP, live auth, or strategy-active changes were made.

## Verification

- Local Rust targeted tests:
  - `strategy_params`: 15 passed
  - `test_grid_blocked_symbol_skips_open_but_allows_close`: 1 passed
  - `test_load_strategy_params_from_file`: 1 passed
- `git diff --check`: PASS
- Linux deploy: `git pull --ff-only` + `restart_all.sh --rebuild --keep-auth`
- Runtime: engine PID `794012`, API PID `794081`, watchdog fresh for paper/demo/live snapshots.
- Linux TOML readback confirms `grid_levels = 7` and the blocked list.

## Immediate Healthcheck Baseline

Post-restart passive healthcheck still SUMMARY FAIL because `[38]` uses a 24h window:

- demo: n=37, p50=4.1m, fee_burn=0.23, re-entry=0.39
- live_demo: n=98, p50=1.7m, fee_burn=0.45, re-entry=0.71

This is the expected starting baseline, not a deploy failure. `[22]`, order/fill consistency, and maker-entry intent shape all passed.

## Acceptance Window

Start the observation clock from commit `6fdcc91` restart. First useful read:

- 6h: live_demo re-entry should drop materially below 0.71.
- 24h: target live_demo re-entry <= 0.60 and lifetime_ratio >= 0.50.
