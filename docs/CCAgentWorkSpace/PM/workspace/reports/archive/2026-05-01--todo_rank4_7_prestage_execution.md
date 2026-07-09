# TODO Rank 4-7 pre-stage execution

Date: 2026-05-01
Scope: Complete the operator-selected TODO 1-4 batch and update active state.
Status: Complete; source/RFC pushed after final doc sync

## Summary

Checkpoint `ec8f0f4` completed the four selected items:

- Rank 4 STRK-FUP healthcheck: broader silent-dead RFC for `[3]`, `[19]`, `[23]`, `[24]`, and `[26]`; `[27]` remains governed by the earlier `4abb36a` semantics.
- Rank 5 G7-04 Phase B/C: pure downside-CUSUM evaluator plus a dormant orchestrator filter hook; production hot path is not enabled.
- Rank 6 G4-03 Phase B: canary promoting rows now have Brier/PSI quality gates; cron wrapper is default dry-run, apply is env-gated, and SIGHUP is opt-in.
- Rank 7 LG-4: supervised live gate RFC for operator approval, risk-limit overrides, kill switch, and audit mirror.

## Verification

- `cargo fmt --check`
- `cargo test -p openclaw_engine --lib cusum -- --test-threads=1` -> 17/0
- `python3 -m pytest program_code/ml_training/tests/test_canary_promoter.py` -> 21/0
- `python3 -m py_compile program_code/ml_training/canary_promoter.py helper_scripts/db/canary_promote_runner.py`
- `bash -n helper_scripts/db/canary_promote_cron.sh`
- hard-coded home path scan on the new files
- `git diff --check`

## Runtime State

- No rebuild or restart was performed.
- Rust engine runtime remains the `daab51c` scanner deploy.
- Linux source fast-forwarded to `21ecbf6`.
- Latest post-sync wrapper sample at 2026-05-01 22:21 CEST was SUMMARY FAIL exit 1 due `[22] trading_pipeline_silent_gap`.
- Read-only split: recent live_demo orders are `Working` PostOnly limits; recent demo risk is rejected-only. This is not yet proven writer/order-push wedge and should be treated as `[22]` semantic calibration before restart-style action.
- `[27]` remains WARN because current recent demo verdicts are rejected-only (`approved_verdicts_30m=0`), not a persisted-intent writer wedge.

## Boundary

No trading, risk/strategy parameter, live authorization, DB write, cron installation, SIGHUP, rebuild, restart, or deploy action was performed.

G7-04 remains dormant until a later explicit hot-path wiring task. G4-03 canary promotion remains default dry-run and requires both cron/apply env gates before any state transition.
