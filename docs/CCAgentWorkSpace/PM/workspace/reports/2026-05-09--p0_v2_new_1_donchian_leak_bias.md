# P0-V2-NEW-1 Donchian Leak-Bias Checkpoint

Date: 2026-05-09
Role: PM
Status: SOURCE/TEST CLOSED

## Scope

Closed `P0-V2-NEW-1-DONCHIAN-LEAK-BIAS` at the source/test level.

The important distinction is that `openclaw_core::indicators::donchian()` remains
the explicit inclusive helper, but runtime indicator snapshots are produced by
`IndicatorEngine::compute_all_with_lambda()` through `donchian_prior()`.

This checkpoint adds regression coverage for the actual runtime evidence path:

- `openclaw_core::indicators` now proves current-bar high/low spikes are
  excluded from `IndicatorEngine::compute_all()` Donchian snapshots.
- `openclaw_engine::strategies::bb_breakout` now proves 5m hard-gate entry uses
  the prior-bar Donchian upper, not a current-bar-inclusive high spike.

## Verification

- `cargo test -p openclaw_core indicators::tests -- --nocapture`
  -> 7 passed
- `cargo test -p openclaw_engine --lib strategies::bb_breakout -- --nocapture`
  -> 74 passed
- `cargo fmt --all --check`
- `git diff --check`

## Boundary

Source/test only. No strategy pause, runtime reload, rebuild, DB write, cron/env
mutation, provider traffic, live auth mutation, or true-live API action.

PM SIGN-OFF: APPROVED for source/test close.
