# W-AUDIT-6 bb_breakout Cooldown Drift Checkpoint

Date: 2026-05-09
Role: PM
Status: SOURCE/TEST PARTIAL

## Scope

This checkpoint closes the narrow W-AUDIT-6/QC finding:

- `BbBreakoutParams::default().cooldown_ms` was `300_000`.
- `BbBreakout::new()` seeded runtime cooldown as `600_000`.
- The constructor now shares `DEFAULT_COOLDOWN_MS=300_000` with the params default.
- Regression coverage asserts both `BbBreakout.cooldown_ms` and the underlying
  `TrendCooldown` duration match `BbBreakoutParams::default().cooldown_ms`.

## Verification

- `cargo test -p openclaw_engine strategies::bb_breakout --lib`
  - 70 passed
- `git diff --check`
  - passed

The Rust test command still prints existing unrelated warnings:
unused imports in `claude_teacher/applier_test_fixtures.rs`,
`ws_client/dispatch.rs`, and `ai_budget/tracker.rs`; one dead field in
`funding_arb.rs`; one unused method in `grid_trading/position_mgmt.rs`.

## Boundary

Source/test/docs only. No strategy/risk TOML mutation, no backend or engine
start, no rebuild, restart, deploy, DB write/apply, live auth mutation, scanner
authority change, Executor hard authority, MAG-083/MAG-084 unlock, or true-live
API action.

PM SIGN-OFF: APPROVED for this partial checkpoint.
