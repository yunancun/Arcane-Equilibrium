# W-AUDIT-6 Per-Trade Risk SSOT Checkpoint

Date: 2026-05-09
Role: PM
Status: SOURCE/TEST PARTIAL

## Scope

This checkpoint closes the W-AUDIT-6 `per_trade_risk_pct` double-source gap:

- `RiskConfig.limits.per_trade_risk_pct` is the authoritative cold-start sizing
  source for Kelly.
- Shared constants now define the validated/runtime bounds:
  - `MIN_PER_TRADE_RISK_PCT = 0.001`
  - `MAX_PER_TRADE_RISK_PCT = 0.20`
  - `DEFAULT_PER_TRADE_RISK_PCT = 0.03`
- `GlobalLimits::validate()` now rejects values below `0.001` instead of
  accepting a value that runtime sizing later clamps.
- `KellyConfig::from_risk_config()` derives `risk_pct` and Kelly tier fractions
  from the active `RiskConfig`.
- `replay_runner` and replay regression tests now use the same constructor.
- `IntentProcessor::update_risk_config()` re-anchors an existing Kelly config
  after risk hot-reload so P1 risk cap and Kelly cold-start sizing stay aligned.

## Verification

- `cargo test -p openclaw_engine kelly --lib`
  - 23 passed
- `cargo test -p openclaw_engine risk_config --lib`
  - 138 passed
- `cargo test -p openclaw_engine intent_processor --lib`
  - 116 passed
- `cargo check -p openclaw_engine --bin replay_runner --features replay_isolated`
  - passed
- `cargo fmt --all -- --check`
  - passed
- `git diff --check`
  - passed

The Rust commands still print existing unrelated warnings in modules such as
`claude_teacher`, `ipc_server`, `ws_client`, `ai_budget`, `funding_arb`, and
`grid_trading`.

## Boundary

Source/test only. No risk TOML mutation, runtime config reload, backend or
engine start, rebuild, restart, deploy, DB write/apply, live auth mutation,
strategy activation, scanner authority change, Executor hard authority,
MAG-083/MAG-084 unlock, or true-live API action.

PM SIGN-OFF: APPROVED for this partial checkpoint.
