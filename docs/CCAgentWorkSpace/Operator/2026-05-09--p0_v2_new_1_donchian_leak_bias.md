# P0-V2-NEW-1 Donchian Leak-Bias Operator Note

Date: 2026-05-09
Status: SOURCE/TEST CLOSED

## What Changed

`P0-V2-NEW-1-DONCHIAN-LEAK-BIAS` is closed at source/test level.

Runtime Donchian evidence is locked to prior-bar snapshots:

- core `IndicatorEngine::compute_all()` excludes current-bar high/low spikes;
- `bb_breakout` 5m hard-gate entry uses that prior-bar upper and is covered by a
  dedicated regression.

The inclusive `donchian()` helper was not changed globally because it has clear
standalone semantics. Runtime snapshots already use `donchian_prior()`, and the
new tests prevent that path from regressing silently.

## Verification

- `cargo test -p openclaw_core indicators::tests -- --nocapture`
- `cargo test -p openclaw_engine --lib strategies::bb_breakout -- --nocapture`
- `cargo fmt --all --check`
- `git diff --check`

## Boundary

No rebuild/restart, no DB write, no strategy activation change, no live auth
mutation, and no provider/API traffic.
