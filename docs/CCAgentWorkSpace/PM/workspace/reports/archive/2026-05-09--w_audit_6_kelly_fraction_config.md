# W-AUDIT-6 Kelly Fraction Config Checkpoint

Date: 2026-05-09
Role: PM
Status: SOURCE/TEST PARTIAL

## Scope

This checkpoint closes the W-AUDIT-6 Kelly tier magic-literal gap without
changing default behavior:

- `RiskConfig.kelly` now exposes:
  - `young_fraction = 0.125`
  - `mature_fraction = 0.16666666666666666`
  - `established_fraction = 0.25`
- `ml::kelly_sizer::KellyConfig` carries the same fields.
- `compute_kelly_qty()` now multiplies by the configured fraction instead of
  hardcoded `/ 8`, `/ 6`, `/ 4` divisors.
- Replay runner KellyConfig construction passes the fractions through from the
  deserialized `RiskConfig`.
- All risk TOMLs expose behavior-preserving defaults.

## Verification

- `cargo test -p openclaw_engine kelly --lib`
  - 21 passed
- `cargo test -p openclaw_engine risk_config --lib`
  - 130 passed
- `cargo check -p openclaw_engine --bin replay_runner --features replay_isolated`
  - passed
- `git diff --check`
  - passed

The Rust commands still print existing unrelated warnings in modules such as
`claude_teacher`, `ipc_server`, `ws_client`, `ai_budget`, `funding_arb`, and
`grid_trading`.

## Boundary

Source/test/config-surface only. No runtime config reload, no backend or engine
start, no rebuild, restart, deploy, DB write/apply, live auth mutation, strategy
activation, scanner authority change, Executor hard authority, MAG-083/MAG-084
unlock, or true-live API action.

PM SIGN-OFF: APPROVED for this partial checkpoint.
