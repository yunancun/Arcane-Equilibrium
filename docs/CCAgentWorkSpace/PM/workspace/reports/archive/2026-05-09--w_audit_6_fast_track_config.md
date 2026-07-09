# W-AUDIT-6 fast_track Threshold Config

Date: 2026-05-09
Owner: PM local implementation
Scope: source/test/config-surface only

## Summary

Closed the W-AUDIT-6 fast_track hardcoded-threshold gap by moving the held-drop
`15%` / `5% + 3σ` triggers into `RiskConfig.fast_track`.

Defaults preserve the previous runtime behavior:

- `extreme_drop_pct = 15.0`
- `moderate_drop_pct = 5.0`
- `outlier_sigma_threshold = 3.0`

The margin-crisis `90%` threshold remains in `fast_track.rs` as a physical
exchange-safety constant, not an operator strategy knob.

## Implementation

- Added `risk_config_fast_track.rs` sibling module to keep `risk_config.rs`
  under the local file-size discipline.
- Added `RiskConfig.fast_track` with validation and serde defaults.
- Wired Step 0 to use `evaluate_fast_track_with_config()` and
  `is_drop_scoped_reduce_with_config()`.
- Updated sigma-scaled ReduceToHalf cooldown to scale by the configured trigger
  sigma.
- Added `[fast_track]` defaults to the base, paper, demo, and live risk TOMLs.
- Added regression coverage for defaults, validation, TOML round-trip, custom
  thresholds, and configured sigma cooldown scaling.

## Verification

- `cargo fmt --all`
- `cargo test -p openclaw_engine fast_track --lib` PASS (51/0)
- `cargo test -p openclaw_engine risk_config --lib` PASS (134/0)
- `cargo check -p openclaw_engine --bin openclaw-engine` PASS
- `git diff --check` PASS

Existing unrelated Rust warnings remain in `claude_teacher`, `ws_client`,
`ai_budget`, `funding_arb`, `grid_trading`, and non-test IPC/task paths.

## Boundary

No rebuild, restart, deploy, live auth mutation, strategy activation,
MAG-083/MAG-084 unlock, DB write, or true-live action was performed.
