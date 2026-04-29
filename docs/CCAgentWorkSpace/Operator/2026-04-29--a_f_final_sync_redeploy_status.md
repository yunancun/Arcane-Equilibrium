# A-F Final Sync + Linux Redeploy Status

Date: 2026-04-29 CEST
Role: PM

## Scope

- Confirmed 62-finding remediation Batch A-F is committed, pushed, and synced.
- Fixed a deploy ownership bug in lifecycle scripts so uvicorn master/workers are recognized by cwd when command lines do not include `control_api_v1`.
- Completed Linux `restart_all.sh --rebuild --keep-auth` redeploy on `trade-core`.

## Commits

- `bc3fa70` — `fix(audit): close 62-finding remediation batches`
- `6539e4e` — `docs: record audit remediation sync state`
- `5db4e29` — `fix(deploy): recognize api uvicorn cwd during restart`

## Verification

- `bash -n helper_scripts/restart_all.sh helper_scripts/stop_all.sh helper_scripts/clean_restart.sh helper_scripts/fresh_start.sh`
- `pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_e_runtime_ownership.py` → 10 passed
- `git diff --check`
- Linux redeploy command: `PATH="$HOME/.cargo/bin:$PATH" bash helper_scripts/restart_all.sh --rebuild --keep-auth`

## Runtime Result

- Engine PID: `161957` (`openclaw-engine`)
- API master PID: `162029` plus four uvicorn workers
- Port `8000` is bound by the new control API venv
- Watchdog: `engine_alive=true`, demo snapshot fresh
- Direct unauth health probes return 401, which confirms auth enforcement; GUI-origin API requests return 200 OK

## PM Verdict

CONDITIONAL / NOT FULL GREEN.

`passive_wait_healthcheck.sh --quiet` still reports:

- FAIL `[12] bb_breakout_post_deadlock_fix`
- FAIL `[22] trading_pipeline_silent_gap`
- WARN `[27] intents_counter_freeze`
- WARN `[31] edge_diag_2_strategy_diversity`

The earlier startup-transient `[16] strategist_cycle_fresh` cleared after the first 5-minute cycle.

Live pipeline refusal is expected after Batch A auth hardening: existing signed authorization is schema v1, while the engine expects schema v2. Operator must renew through `/api/v1/live/auth/renew` or renew-review. Do not hand-write `authorization.json`.

## Next Gate

Before any full-green / production-ready statement, investigate `[22] trading_pipeline_silent_gap` and the current fee-rate cold-boot cost_gate fail-closed behavior, then rerun passive healthcheck.
