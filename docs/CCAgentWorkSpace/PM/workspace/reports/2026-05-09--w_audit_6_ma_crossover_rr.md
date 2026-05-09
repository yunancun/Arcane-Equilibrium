# W-AUDIT-6 ma_crossover R:R Trailing/TP

Date: 2026-05-09
Role: PM/E1 local execution
Scope: W-AUDIT-6 source/test checkpoint

## Summary

- Added `StrategyOverride.take_profit_enforced_override` so one strategy can enforce TP without turning on global `limits.take_profit_enforced`.
- Wired risk checks to read that effective per-strategy TP enforcement flag before the existing TP gate.
- Bound `ma_crossover` exits in all four `settings/risk_control_rules/risk_config*.toml` files:
  - `stop_loss_max_pct_override = 2.5`
  - `take_profit_max_pct_override = 8.0`
  - `take_profit_enforced_override = true`
  - `trailing_activation_pct_override = 0.6`
  - `trailing_distance_pct_override = 0.4`
- Kept the change strategy-scoped; grid / BB strategies continue to use global TP behavior.

## Verification

- `cargo test -p openclaw_engine --lib w_audit_6` — 14 passed.
- `cargo test -p openclaw_engine --lib test_g2_03_real_toml_files_load_with_ma_crossover_section` — 1 passed.
- `cargo test -p openclaw_engine --lib test_demo_toml_retired_funding_arb_removed_from_risk_config` — 1 passed.
- `cargo test -p openclaw_engine --lib test_g2_03_strategy_override_toml_round_trip_with_overrides` — 1 passed.
- `cargo test -p openclaw_engine --lib` — 2580 passed.
- `git diff --check` — passed.

## Runtime Boundary

This source/test checkpoint is intended to be runtime-loaded by the operator-requested three-side sync and rebuild/restart in the same session. It does not enable true mainnet API access, mutate live auth, activate retired strategies, or change scanner authority.
