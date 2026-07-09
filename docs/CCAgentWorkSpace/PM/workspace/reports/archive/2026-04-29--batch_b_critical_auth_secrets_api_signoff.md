# Batch B Critical Auth / Secrets / API Exposure Sign-off

Date: 2026-04-29 CEST
Owner: PM
Status: fixed, uncommitted

## Scope

Batch B closes 14 findings:

- `DAPI-001` through `DAPI-006`
- `RC-003`
- `SC-001` through `SC-007`

Required chain executed:

- PM -> E3(explorer) + PA(default) -> E1/E1a(worker) -> E2(explorer) -> E4(worker) -> PM

## Changes

- Added shared operator+scope gates for high-risk write routes: AI budget, risk, paper/demo, live session/close/authority, strategy writes, executor shadow-toggle, scheduled restart, and ML promote.
- Server audit identity now comes from the authenticated actor for AI budget writes; client-supplied `updated_by` is ignored.
- Dashboard HTML, DB health, and model registry reads are authenticated; DB/model error details are redacted.
- `/openclaw/*` proxy now forwards only a header allowlist, stripping Cookie and Authorization by default.
- API bearer handling rejects placeholders, supports strict mode, and no longer prints auto-generated token values.
- GUI password loading rejects blank or placeholder values; cookie `Secure` can be forced or derived from trusted proxy headers.
- Grafana provisioning no longer stores committed bearer/Postgres/admin credentials; anonymous access is off by default and host binding defaults to `127.0.0.1`.
- Runtime scripts moved DB URL / IPC HMAC values to 0600 secret files and pass only `*_FILE` paths to long-lived engine/API processes; migration scripts use `PGPASSFILE`; curl callers use 0600 config/payload files.
- Rust engine and Python API now resolve `OPENCLAW_DATABASE_URL_FILE` and `OPENCLAW_IPC_SECRET_FILE` while preserving direct-env compatibility.

## Verification

- `PYTHONDONTWRITEBYTECODE=1 /tmp/openclaw-batch-a-venv/bin/python -m pytest -p no:cacheprovider program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_b_security_auth.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_ai_budget_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_reset_drawdown_route.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_shadow_toggle_api.py -q` -> 47 passed.
- `py_compile` on touched Python API/test files -> passed.
- `bash -n` on modified shell scripts -> passed.
- `plutil -lint` on modified launchd plists -> passed.
- `docker-compose config` for control API and monitoring with dummy secrets -> passed; control API compose still emits an existing obsolete `version` warning.
- `cargo check -p openclaw_engine --manifest-path rust/Cargo.toml` -> passed with existing unused/dead-code warnings.
- `git diff --check` -> passed.
- Targeted static sweep found no Batch B residuals for password-bearing `psql "$DSN"`, tokenized Telegram URL, default `change-me` API token docs, `3000:3000` Grafana bind, proxy Cookie/Auth forwarding, or long-lived `OPENCLAW_IPC_SECRET="${...}"` launch paths.

## Notes

- No deploy, restart, or runtime mutation was performed.
- `cargo fmt --all --check` is currently blocked by broad pre-existing Rust formatting drift outside this batch; no repo-wide formatting rewrite was made.
- Tracking ledger updated in `docs/audit/remediation_tracking.md`.
