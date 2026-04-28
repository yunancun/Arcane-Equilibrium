# Batch A Live Boundary Freeze Signoff

Date: 2026-04-28
Owner: PM
Scope: LP-001, OE-007, OS-001, RC-001, SW-002
Status: fixed locally, not deployed

## Summary

Batch A freezes live write boundaries so normal operator/API/script paths cannot mutate live exchange state outside exact `live_reserved` and the Rust live pipeline.

Implemented controls:
- Live authorization schema v2 includes `approved_system_mode=live_reserved` in the signed payload.
- Python renew/review and executor/strategist live gates require exact `global_mode_state == "live_reserved"`.
- Python/Rust verifiers reject v1, missing mode, non-live mode, expired auth, wrong env, and bad signature.
- Python live close REST fallback is disabled; live channel unavailable returns operator-visible 409/blocked results.
- Restart flatten scripts no longer perform direct mainnet REST flatten; `clean_restart_flatten.py --env mainnet` exits nonzero unless dry-run.
- Rust exchange emergency close paths enqueue reduce-only closes before local flatten; send failure leaves local position open and does not mark `pending_close`.
- Live command dispatch now uses dynamic `LiveCmdSenderSlot` for reconciler, strategist promote, edge reload, IPC, and watcher teardown/respawn.

## Verification

Python:
- `/tmp/openclaw-batch-a-venv/bin/python -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_live_authorization_signing.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_shadow_toggle_api.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_promote_api.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_live_auth_recheck_trigger.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_live_gate_fallback.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_operator_live_flatten_boundary.py` -> 69 passed.
- `python3 -m py_compile` on touched Python files -> passed.

Rust:
- `cargo test --release -p openclaw_engine live_authorization --lib` -> 18 passed.
- `cargo test --release -p openclaw_engine tick_pipeline::tests::dual_rail_dispatch --lib` -> 13 passed.
- `cargo test --release -p openclaw_engine strategist_scheduler::tests --lib` -> 26 passed.
- `cargo test --release -p openclaw_engine main_boot_tasks::edge_reload_tests --bin openclaw-engine` -> 13 passed.
- `cargo test --release -p openclaw_engine live_auth_watcher --bin openclaw-engine` -> 10 passed.

Review:
- E2 initial adversarial review blocked on stale Python v1 auth verifier in `executor_routes.py`.
- E2 follow-up review accepted after executor/strategist/auth signing tests were upgraded to schema v2.
- E4 regression verifier passed release-mode Rust filters, Python tests, `rg` fallback scans, and `git diff --check`.

## Operational Notes

No deploy, restart, or Linux sync was performed. Linux `trade-core` preflight at Batch A start showed `engine_alive=true`, `demo/live=true`, `paper=false`; that runtime/docs drift remains a separate E4 baseline item before any deployment.

The local worktree contains unrelated pre-existing/user edits outside Batch A. Batch A signoff applies to the files and verification above only.
