# Batch E Operator / Runtime Ownership Sign-off

Date: 2026-04-29 CEST
Owner: PM
Status: fixed, uncommitted

## Scope

Batch E closes 13 findings:

- `SW-001`
- `SW-003`
- `SW-004`
- `SW-005`
- `SW-006`
- `SW-007`
- `OS-002`
- `OS-003`
- `OS-004`
- `OS-005`
- `OS-006`
- `OS-007`
- `DAPI-007`

Required chain executed:

- PM -> E3(explorer) + PA(default) -> E1/E1a/TW(worker) -> E2(explorer) -> E4(worker) -> PM

## Changes

- `POST /api/v1/system/scheduled-restart` is now disabled (`HTTP 410`) and explicitly redirected to service-manager/operator-script ownership (`launchctl`/`systemctl` or `helper_scripts/restart_all.sh`).
- `clean_restart.sh` and `fresh_start.sh` now set maintenance flag before stop, guard cleanup with `EXIT/INT/TERM` traps, and use validated API PID shutdown to avoid killing unrelated `:8000` services.
- `fresh_start_reset.py` execute confirmation is now DSN/environment fingerprinted; `fresh_start.sh` requires explicit `--db-reset-confirm=...` and no longer auto-generates a confirm token.
- `restart_all.sh`, `stop_all.sh`, `clean_restart.sh`, and `fresh_start.sh` now use validated engine PID ownership:
  - accepted engine PIDs must match this repo's binary path or run from this repo cwd with the expected engine command.
  - broad engine `pkill -f` patterns were removed.
- Added `helper_scripts/deploy/launchd_preflight.sh` and updated deploy runbook to enforce preflight-before-load, including plist placeholder checks and secret-file readiness.
- `mac_bootstrap_db.sh` now creates `trading_admin` as least-privilege (`NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION`), binds password via psql variable substitution, and uses a properly closed SQL heredoc.
- Added overlap lock guards (`mkdir` lockdir + trap cleanup) for cron wrappers:
  - `helper_scripts/cron_daily_report.sh`
  - `helper_scripts/cron_observer_cycle.sh`
  - `helper_scripts/db/counterfactual_daily_cron.sh`
  - `helper_scripts/db/passive_wait_healthcheck_cron.sh`
- `cron_daily_report.sh` now builds Telegram payload via `jq` and uses `curl --config` + payload file so tokenized URL and shell-interpolated JSON no longer appear in argv.
- Multi-worker ownership hardening:
  - Evolution scheduler leader election lock (`flock`) with non-leader skip path.
  - Reconciler alert monitor leader lock.
  - Grafana writer leader lock and non-leader skip logging.
  - ExperimentLedger now persists EXPIRY transitions via debounced save.

## Verification

- `bash -n helper_scripts/clean_restart.sh helper_scripts/fresh_start.sh helper_scripts/restart_all.sh helper_scripts/stop_all.sh helper_scripts/cron_daily_report.sh helper_scripts/cron_observer_cycle.sh helper_scripts/db/counterfactual_daily_cron.sh helper_scripts/db/passive_wait_healthcheck_cron.sh helper_scripts/deploy/launchd_preflight.sh helper_scripts/mac_bootstrap_db.sh` -> passed.
- `/tmp/openclaw-batch-a-venv/bin/python -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_legacy_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/evolution_auto_scheduler.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/experiment_ledger.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_wiring.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/grafana_data_writer.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py helper_scripts/db/fresh_start_reset.py` -> passed.
- `PYTHONDONTWRITEBYTECODE=1 /tmp/openclaw-batch-a-venv/bin/python -m pytest -p no:cacheprovider program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_e_runtime_ownership.py -q --tb=short` -> 10 passed.
- `PYTHONDONTWRITEBYTECODE=1 /tmp/openclaw-batch-a-venv/bin/python -m pytest -p no:cacheprovider program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_b_security_auth.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_e_runtime_ownership.py -q --tb=short` -> 20 passed.
- `PYTHONDONTWRITEBYTECODE=1 /tmp/openclaw-batch-a-venv/bin/python -m pytest -p no:cacheprovider program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_d_risk_fail_closed.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_e_runtime_ownership.py -q --tb=short` -> 18 passed.
- `rg -n 'pkill -f|pkill -TERM -f|pkill -KILL -f|cat >> "\$TMP_SQL"|ENGINE_CMD_FRAGMENT' helper_scripts/mac_bootstrap_db.sh helper_scripts/restart_all.sh helper_scripts/stop_all.sh helper_scripts/clean_restart.sh helper_scripts/fresh_start.sh` -> no matches.
- A-E Python targeted suite -> 128 passed, 22 existing Pydantic warnings.
- Rust full lib suite: `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml --lib` -> 2355 passed.
- Local release rebuild: `cargo build --release -p openclaw_engine --manifest-path rust/Cargo.toml` -> passed with existing warnings.
- `git diff --check` -> passed.

## Notes

- `cron_daily_report.sh` received an extra follow-up in this pass: lock cleanup now runs even when env validation exits early, preventing stale lock drift.
- Follow-up reassessment confirmed the earlier `OS-003` and `OS-006` gaps were real; both are now patched and covered by tests/static checks above.
- No deploy, restart, commit, or push was performed.
- Tracking ledger updated in `docs/audit/remediation_tracking.md`.
