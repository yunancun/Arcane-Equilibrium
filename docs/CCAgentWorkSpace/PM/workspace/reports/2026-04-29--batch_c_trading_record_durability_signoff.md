# Batch C Trading Record Durability Sign-off

Date: 2026-04-29 CEST
Owner: PM
Status: fixed, uncommitted

## Scope

Batch C closes 12 findings:

- `OE-001` through `OE-005`
- `OE-008`
- `OE-009`
- `DBW-001` through `DBW-005`

Required chain executed:

- PM -> PA(default) + FA(default) -> E1/E1a(worker) -> E2(explorer) -> E4(worker) -> PM

## Changes

- Private websocket parsing now preserves multi-event payloads for orders, executions, positions, and wallets.
- Dispatch failures now emit terminal pending-order events so rejected/failed orders leave pending state and produce order state changes.
- DB batch writers now retain or requeue rows on pool unavailability, SQL failure, or failed chunks instead of clearing buffers blindly.
- Fill persistence now prefers Bybit execution ids for deterministic fill idempotency.
- Early execution fallback no longer attributes ambiguous fills to an arbitrary pending order.
- Demo/live stop and close-all responses now report partial failures explicitly through `status`, `closed_all`, `partial_failure`, `errors`, and verify data.
- Risk verdict writes now persist risk level plus passed/failed checks.
- The exit-features migration was moved out of excluded `V999` into eligible `V029`, and migration filtering tests cover the rule.
- High-value trading writer sends now use explicit drop accounting/logging.
- Python DB pool return now rolls back before reuse and closes dirty connections if rollback fails.
- Auto-migrate with no DB pool now fails closed unless `OPENCLAW_ALLOW_DBLESS=1` is set.

## Verification

- `rustfmt --edition 2021` on touched Rust files -> passed.
- `cargo check -p openclaw_engine --manifest-path rust/Cargo.toml` -> passed with existing unused/dead-code warnings.
- `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml bybit_private_ws --lib` -> 31 passed.
- `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml pending_registration_order_type_tests --lib` -> 8 passed.
- `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml emit_close_fill --lib` -> 13 passed.
- `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml batch_insert --lib` -> 10 passed.
- `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml migrations --lib` -> 15 passed.
- `/tmp/openclaw-batch-a-venv/bin/python -m py_compile` on touched Python API files -> passed.
- `/tmp/openclaw-batch-a-venv/bin/python -m pytest -p no:cacheprovider program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_db_pool_connection_reset.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_session_stop_cancel_verify.py -q --tb=short` -> 14 passed, 11 existing warnings.

## Notes

- E4 initially found three 401s in direct handler tests after Batch B auth hardening; the tests now pass authenticated actors with `operator` role and required scopes.
- No deploy, restart, commit, or push was performed.
- Tracking ledger updated in `docs/audit/remediation_tracking.md`.
