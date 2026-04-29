# Batch D Risk / Config Fail-Closed Sign-off

Date: 2026-04-29 CEST
Owner: PM
Status: fixed, uncommitted

## Scope

Batch D closes 8 findings:

- `RC-002`
- `RC-004`
- `RC-005`
- `RC-006`
- `SADF-002`
- `SADF-003`
- `LP-002`
- `OE-006`

Required chain executed:

- PM -> CC(default) + PA(default) -> E1/E1a(worker) -> E2(explorer) -> E4(worker) -> PM

## Changes

- H0 periodic status refresh no longer resets cooldown/kill-switch state:
  - added `H0Gate::risk_snapshot()` and merged status refresh via `build_status_risk_snapshot(...)`.
- Startup config loading now fails closed when demo/live risk config files are missing (no fallback-to-default for those engines).
- Risk-governor tier constraints are enforced consistently at order admission:
  - new-entry blocking on `new_entries_allowed/reduce_only/requires_operator`
  - quantity scaling via governor `position_size_multiplier`
  - reducing/unwind intents are capped to existing position quantity before Guardian/risk checks, so oversized opposite-side intents cannot flip/open.
  - demo/live dispatch marks these capped opposite-side orders as close/reduce-only and skips proactive mirror insertion.
- Legacy IPC `update_risk_config` no longer silently ignores send failures and no longer returns success before application:
  - send failure now returns JSON-RPC internal error
  - success response now waits for event-consumer application ack (`updated=true, queued=false, applied=true`)
  - application/ack timeout returns an error instead of a false success.
- Mixed strategy-params updates are now atomic:
  - typed validation runs before `conf_scale` apply
  - validation failure no longer partially mutates strategy state.
- Demo/Live strategy parameter load errors now fail closed to all-inactive strategy configs; Paper keeps exploration default fallback.
- `clean_restart.sh` / `fresh_start.sh` package checks/builds use canonical `openclaw_engine` package id (`cargo pkgid -p openclaw_engine` / `cargo build -p openclaw_engine`).
- Close dispatch retry path now has real per-attempt timeout budget (`CLOSE_ATTEMPT_TIMEOUT_MS=500`) so "fast-exit" is wall-clock bounded, not just sleep-delays.

## Verification

- `PYTHONDONTWRITEBYTECODE=1 /tmp/openclaw-batch-a-venv/bin/python -m pytest -p no:cacheprovider program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_d_risk_fail_closed.py -q --tb=short` -> 8 passed.
- `PYTHONDONTWRITEBYTECODE=1 /tmp/openclaw-batch-a-venv/bin/python -m pytest -p no:cacheprovider program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_d_risk_fail_closed.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_e_runtime_ownership.py -q --tb=short` -> 18 passed.
- `cargo check -p openclaw_engine --manifest-path rust/Cargo.toml` -> passed with existing warnings.
- Rust targeted tests:
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml status_risk_snapshot_preserves_active_cooldown_and_kill_switch --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_load_unified_configs_missing_demo_live_is_error --bin openclaw-engine` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_governor_reduced_blocks_new_entries --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_governor_cautious_scales_new_entry_qty --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_governor_reduced_caps_opposite_order_to_existing_qty --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_governor_reduced_caps_exchange_opposite_order_to_existing_qty --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_conf_scale_not_partially_applied_when_typed_validation_fails --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_e4_5_handle_update_risk_config_send_failure_returns_internal_error --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_e4_5_handle_update_risk_config_happy_single_param_returns_applied_true --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_load_strategy_params_missing_file_demo_is_fail_closed_inactive --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_load_strategy_params_invalid_toml_live_is_fail_closed_inactive --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_close_attempt_timeout_constant_is_500ms --lib` -> 1 passed.
- Regression:
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml intent_processor::tests:: --lib` -> 86 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml --lib` -> 2355 passed.
  - `cargo build --release -p openclaw_engine --manifest-path rust/Cargo.toml` -> passed with existing warnings.
  - A-E Python targeted suite -> 128 passed, 22 existing Pydantic warnings.
  - `git diff --check` -> passed.

## Notes

- Follow-up reassessment confirmed the earlier `RC-005` and `RC-006` semantic gaps were real; both are now patched and covered by tests above.
- No deploy, restart, commit, or push was performed.
- Tracking ledger updated in `docs/audit/remediation_tracking.md`.
