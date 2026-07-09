# W-AUDIT-3 Partial Checkpoint - F-15 / F-17 / SM-05 Draft

Date: 2026-05-09
Role: PM
Status: PARTIAL COMPLETE

## Scope

This checkpoint closes the W-AUDIT-3 items that do not require the unresolved
`P0-DECISION-AUDIT-2` operator decision:

- F-17: Settings tab no longer hardcodes Decision Lease `false`; it reads
  `/api/v1/governance/lease-router/status`.
- F-15: Added Rust regression for router flag ON -> Production lease ->
  transition writer channel, plus opt-in `OPENCLAW_TEST_PG` DB-row e2e.
- SM-05 draft: Added AMD-2026-05-09-01 documenting `ExecutorConfigCache`
  polling, fail-closed default, last-good retention, and provider exception
  behavior.
- Warning cleanup: removed one now-unused `tokio::sync::mpsc` import from
  `startup/mod.rs`.

## Still Blocked

F-01 remains blocked by `P0-DECISION-AUDIT-2`. This checkpoint does not decide
whether the 5-Agent Executor path is temporary demo promotion capable or
permanently shadow-only.

## Verification

- `python3 -m py_compile .../app/governance_routes.py`
- `python3 -m pytest .../tests/test_governance_routes_coverage.py -q` -> 113 passed
- `python3 -m pytest .../tests/static/test_replay_subtab_static_assets.py -q` -> 48 passed
- `cargo fmt --all`
- `cargo test -p openclaw_engine --test lease_flag_flip_e2e router_flag_flip_emits_writer_channel_transitions -q` -> 1 passed
- `cargo test -p openclaw_engine --test lease_flag_flip_e2e router_flag_flip_writes_lease_transition_rows_when_test_pg_present -q` -> 1 passed, DB work is opt-in and returned early when `OPENCLAW_TEST_PG` was unset
- `cargo test -p openclaw_engine risk_runtime_status_surfaces_lease_router_flag -q` -> 1 passed
- `cargo check -p openclaw_engine --bin openclaw-engine` -> passed with pre-existing Rust warnings
- `git diff --check`

## Boundary

Source/test/docs only. No rebuild, restart, runtime env flip, live auth
mutation, scanner authority change, Executor hard authority, strategy/risk
config mutation, MAG-083 approval, MAG-084 approval, or true-live API action.

PM SIGN-OFF: APPROVED for this partial checkpoint.
