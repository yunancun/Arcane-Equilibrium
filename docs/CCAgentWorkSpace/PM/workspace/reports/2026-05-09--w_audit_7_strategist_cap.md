# W-AUDIT-7 F-strategist-cap Checkpoint

Date: 2026-05-09
Role: PM
Status: SOURCE/TEST CLOSED

## Scope

This checkpoint closes the source-only F-strategist-cap task.

- Raised `settings/risk_control_rules/risk_config_{paper,demo,live}.toml`
  `strategist.max_param_delta_pct` from `0.30` to `0.50`.
- Aligned Rust `StrategistConfig::default()` with the new `0.50` source cap.
- Aligned `strategist_scheduler::DEFAULT_MAX_PARAM_DELTA_PCT` no-store fallback
  with the same `0.50` cap so boot-edge/direct-call paths do not drift from
  serde/TOML defaults.
- Updated scheduler regression coverage so tight overrides still reject, looser
  overrides still hot-reload, and the current default is explicitly pinned.

## Verification

- `cargo fmt --all --check`
- `cargo test -p openclaw_engine --lib strategist_config -- --nocapture`
  -> 7 passed
- `cargo test -p openclaw_engine --lib strategist_scheduler::tests -- --nocapture`
  -> 26 passed
- `git diff --check`

## Boundary

Source/test/docs only. No Linux rebuild, restart, DB write, runtime config reload,
env flip, live auth mutation, scanner authority change, or true-live API action.
The running Linux process will not consume this cap change until a separately
authorized deploy/reload/restart path applies it.

PM SIGN-OFF: APPROVED for source/test close.
