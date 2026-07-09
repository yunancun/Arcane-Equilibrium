# W-AUDIT-7 F-strategist-cap Operator Brief

Date: 2026-05-09
Status: SOURCE/TEST CLOSED

## Result

The strategist non-weight parameter delta cap is now 50% in source:

- `risk_config_paper.toml`, `risk_config_demo.toml`, and
  `risk_config_live.toml` set `max_param_delta_pct = 0.50`.
- Rust `RiskConfig` serde defaults also use `0.50`.
- Scheduler no-store fallback also uses `0.50`.

## Verification

- Rust config tests: 7 passed.
- Rust strategist scheduler tests: 26 passed.
- `cargo fmt --all --check` and `git diff --check` passed.

No rebuild, restart, runtime reload, DB write, env change, live auth mutation, or
true-live API action was performed. Runtime will keep its currently loaded value
until an authorized deploy/reload/restart applies the source change.
