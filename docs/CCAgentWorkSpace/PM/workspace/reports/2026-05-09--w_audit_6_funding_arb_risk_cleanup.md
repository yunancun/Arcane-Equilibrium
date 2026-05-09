# W-AUDIT-6 FundingArb RiskConfig Cleanup Checkpoint

Date: 2026-05-09
Role: PM
Status: SOURCE/TEST PARTIAL

## Scope

This checkpoint closes the W-AUDIT-6 `funding_arb` RiskConfig cleanup:

- Removed `funding_arb` from all four risk TOML files:
  - `settings/risk_control_rules/risk_config.toml`
  - `settings/risk_control_rules/risk_config_paper.toml`
  - `settings/risk_control_rules/risk_config_demo.toml`
  - `settings/risk_control_rules/risk_config_live.toml`
- Kept retirement authority in `strategy_params_{paper,demo,live}.toml`, where
  `funding_arb.active=false` remains explicit for all three runtime modes.
- Added Rust regressions that parse real TOMLs and assert:
  - no `RiskConfig.per_strategy["funding_arb"]`
  - real strategy params keep `funding_arb.active=false`
- Cleaned the existing lib-test warning set by removing unused imports, removing
  the dead `FundingPosition.entry_funding_rate` field, and wiring
  `GridTrading::on_post_only_rejected()` into its existing cooldown helper with
  a regression test.

## Verification

- `rg -n "funding_arb" settings/risk_control_rules/risk_config*.toml`
  - no matches
- `cargo test -p openclaw_engine funding_arb --lib`
  - 38 passed
- `cargo test -p openclaw_engine grid_trading --lib`
  - 45 passed
- `cargo test -p openclaw_engine risk_config --lib`
  - 140 passed
- `cargo test -p openclaw_engine strategy_params --lib`
  - 16 passed
- `cargo test -p openclaw_engine --lib`
  - 2579 passed
- `cargo fmt --all -- --check`
  - passed

The full Rust lib-test run completed without warning output.

## Boundary

Source/test/config cleanup only. No runtime config reload, backend or engine
start, rebuild, restart, deploy, DB write/apply, live auth mutation, strategy
activation, scanner authority change, Executor hard authority, MAG-083/MAG-084
unlock, or true-live API action.

PM SIGN-OFF: APPROVED for this partial checkpoint.
