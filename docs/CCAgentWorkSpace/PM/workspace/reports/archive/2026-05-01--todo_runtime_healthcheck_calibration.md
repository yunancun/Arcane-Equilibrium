# TODO runtime healthcheck calibration

Date: 2026-05-01
Scope: TODO items 1-4 from operator request: runtime/TODO calibration, `[27]` check, `[11]` check, scanner healthcheck documentation.
Status: Complete

## Summary

- Current Mac/Linux source includes `2674e14` (`Fix counterfactual rolling-window healthcheck`).
- Rust engine runtime remains the `daab51c` scanner deploy; no rebuild/restart was performed or required.
- Linux watchdog is healthy: `engine_alive=true`, demo/live fresh, paper inactive by design.
- Post-fix manual healthcheck wrapper at 2026-05-01 21:32 CEST returned SUMMARY WARN exit 0.

## Findings

### [27] intents_counter_freeze

- 2026-05-01 18:00 CEST cron had a real FAIL line for `[27]`.
- Manual wrapper reruns at 21:29 and 21:32 CEST showed `[27]` PASS:
  - demo had recent intents.
  - live_demo had recent intents.
  - live still never produced intents, which is expected.
- Conclusion: transient runtime idle/gating interval, recovered by the time of this batch. No code change was made for `[27]`.

### [11] counterfactual_clean_window_growth

- The 864 -> 413 row drop came from the production replay being a rolling `--days 2` window.
- Old exits naturally aged out of the 48h replay. This is not by itself a DB purge or writer regression.
- Fix `2674e14` changes the healthcheck semantics:
  - rolling-window shrink -> WARN with explicit message.
  - stale JSON >48h -> FAIL remains.
  - non-rolling row regression -> FAIL remains.

## Verification

- `python3 -m py_compile helper_scripts/db/passive_wait_healthcheck/checks_strategy_counterfactual.py helper_scripts/db/test_counterfactual_clean_window_healthcheck.py`
- `python3 helper_scripts/db/test_counterfactual_clean_window_healthcheck.py` -> 2/0
- `python3 helper_scripts/db/test_f7_new_healthchecks.py` -> 39/0
- `git diff --check`
- Linux `git pull --ff-only origin main`
- Linux `bash helper_scripts/db/passive_wait_healthcheck.sh --quiet` -> SUMMARY WARN exit 0

## Documentation Updated

- `TODO.md`
  - Updated runtime/source baseline.
  - Added `[41] scanner_market_gate_confirmation`.
  - Replaced direct Python healthcheck command with wrapper command.
  - Captured `[27]` transient recovery and `[11]` rolling-window WARN semantics.
- `CLAUDE.md`
  - Updated §三 current state to the 2026-05-01 healthcheck/source baseline.
- `docs/CCAgentWorkSpace/PM/memory.md`
  - Added durable PM memory entry for this batch.

## Boundary

No trading, risk, strategy parameter, live authorization, DB write, rebuild, restart, or live deploy action was performed.
