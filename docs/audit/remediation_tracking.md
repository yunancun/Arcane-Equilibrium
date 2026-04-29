# 62-Finding Remediation Tracking

Created: 2026-04-28
Owner: PM
Source: `docs/audit/final_record_zh.md`
Status values: `open`, `in_progress`, `fixed`, `false_positive`, `accepted_risk`

## Batch Status

| Batch | Theme | Count | Status |
| --- | --- | ---: | --- |
| A | Live write boundary freeze | 5 | fixed |
| B | Critical auth / secrets / API exposure | 14 | fixed |
| C | Trading record durability | 12 | fixed |
| D | Risk and config fail-closed | 8 | fixed |
| E | Operator / runtime ownership | 13 | fixed |
| F | ML and agent autonomy readiness | 10 | fixed |
| Total | all audit findings | 62 | 62 represented exactly once |

## Finding Ledger

| ID | Sev | Batch | Status | Owner Chain | Fix Commit | Verification |
| --- | --- | --- | --- | --- | --- | --- |
| LP-001 | P1 | A | fixed | PM -> CC/E3/BB/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | pytest auth/live gate suite + Rust live_authorization |
| OE-007 | P1 | A | fixed | PM -> CC/E3/BB/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | pytest live_gate_fallback + rg no direct live REST fallback |
| OS-001 | P1 | A | fixed | PM -> CC/E3/BB/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | pytest operator_live_flatten_boundary + rg no mainnet script flatten |
| RC-001 | P1 | A | fixed | PM -> CC/E3/BB/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | cargo dual_rail_dispatch + Rust emergency close tests |
| SW-002 | P1 | A | fixed | PM -> CC/E3/BB/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | cargo strategist_scheduler/edge_reload/live_auth_watcher dynamic slot tests |
| DAPI-001 | P1 | B | fixed | PM -> E3/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | pytest ai_budget route auth + server audit actor tests |
| DAPI-002 | P2 | B | fixed | PM -> E3/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | model registry auth/redaction + Batch B static tests |
| DAPI-003 | P2 | B | fixed | PM -> E3/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | proxy header allowlist static regression test; Cookie/Auth stripped |
| DAPI-004 | P2 | B | fixed | PM -> E3/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | pytest dashboard HTML server-side auth |
| DAPI-005 | P2 | B | fixed | PM -> E3/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | pytest DB health auth + generic error response |
| DAPI-006 | P2 | B | fixed | PM -> E3/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | pytest/static high-risk POST operator+scope gates |
| RC-003 | P1 | B | fixed | PM -> E3/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | pytest reset drawdown + risk write scope gates |
| SC-001 | P1 | B | fixed | PM -> E3/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | pytest placeholder reject + generated token not printed |
| SC-002 | P1 | B | fixed | PM -> E3/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | pytest blank/placeholder GUI password rejected |
| SC-003 | P1 | B | fixed | PM -> E3/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | Grafana datasource bearer removed; compose config with dummy secrets |
| SC-004 | P2 | B | fixed | PM -> E3/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | Grafana admin/anonymous env hardening + loopback bind compose check |
| SC-005 | P2 | B | fixed | PM -> E3/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | file-backed DB/IPC secrets, pgpass/curl config, bash/static/cargo checks |
| SC-006 | P2 | B | fixed | PM -> E3/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | provider keys removed from plist template; plutil OK |
| SC-007 | P2 | B | fixed | PM -> E3/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | pytest cookie Secure forced/proxy-trusted modes |
| OE-001 | P1 | C | fixed | PM -> PA/FA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | cargo bybit_private_ws multi-event tests |
| OE-002 | P1 | C | fixed | PM -> PA/FA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | cargo pending_registration dispatch-failed terminal-state tests |
| OE-003 | P1 | C | fixed | PM -> PA/FA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | cargo batch_insert/trading_writer retention checks |
| OE-004 | P1 | C | fixed | PM -> PA/FA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | cargo emit_close_fill exchange exec-id fill-id test |
| OE-005 | P2 | C | fixed | PM -> PA/FA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | cargo ambiguous fill attribution test |
| OE-008 | P2 | C | fixed | PM -> PA/FA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | pytest session stop/close-all partial failure tests |
| OE-009 | P2 | C | fixed | PM -> PA/FA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | cargo check risk verdict schema/writer paths |
| DBW-001 | P1 | C | fixed | PM -> PA/FA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | cargo migrations test excludes V999 and includes V029 |
| DBW-002 | P1 | C | fixed | PM -> PA/FA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | cargo check + explicit try_send drop counter paths |
| DBW-003 | P1 | C | fixed | PM -> PA/FA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | cargo batch_insert outcome + writer requeue tests |
| DBW-004 | P2 | C | fixed | PM -> PA/FA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | pytest db_pool connection rollback/reset tests |
| DBW-005 | P2 | C | fixed | PM -> PA/FA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | cargo migrations dbless auto-migrate fail-closed tests |
| RC-002 | P1 | D | fixed | PM -> CC/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | periodic H0 refresh now preserves active cooldown/kill-switch snapshot fields |
| RC-004 | P1 | D | fixed | PM -> CC/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | startup fail-closed when demo/live risk config files are missing |
| RC-005 | P1 | D | fixed | PM -> CC/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | intent router enforces governor constraints; reduced/circuit-breaker opposite-side orders are capped to existing qty and dispatched reduce-only |
| RC-006 | P2 | D | fixed | PM -> CC/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | legacy `update_risk_config` waits for event-consumer applied ack; send/apply failures now return errors |
| SADF-002 | P2 | D | fixed | PM -> CC/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | mixed strategy params update is atomic; no partial `conf_scale` mutate on validation error |
| SADF-003 | P1 | D | fixed | PM -> CC/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | demo/live strategy params load failures fail-closed to all-inactive config |
| LP-002 | P2 | D | fixed | PM -> CC/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | clean/fresh restart scripts validate/build `openclaw_engine` package id |
| OE-006 | P2 | D | fixed | PM -> CC/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | close dispatch retry path now enforces 500ms per-attempt timeout budget |
| SW-001 | P1 | E | fixed | PM -> E3/PA -> E1/E1a/TW -> E2 -> E4 -> PM | uncommitted | clean/fresh maintenance flag set-before-stop + trap cleanup + safe API stop checks |
| SW-003 | P2 | E | fixed | PM -> E3/PA -> E1/E1a/TW -> E2 -> E4 -> PM | uncommitted | EvolutionScheduler leader lock (`flock`) + non-leader skip startup logs |
| SW-004 | P2 | E | fixed | PM -> E3/PA -> E1/E1a/TW -> E2 -> E4 -> PM | uncommitted | `expire_stale_hypotheses()` now schedules save on EXPIRED transitions |
| SW-005 | P2 | E | fixed | PM -> E3/PA -> E1/E1a/TW -> E2 -> E4 -> PM | uncommitted | reconciler alert monitor leader lock to dedupe multi-worker alerts |
| SW-006 | P2 | E | fixed | PM -> E3/PA -> E1/E1a/TW -> E2 -> E4 -> PM | uncommitted | overlap lock + EXIT/INT/TERM trap on 4 cron wrappers |
| SW-007 | P3 | E | fixed | PM -> E3/PA -> E1/E1a/TW -> E2 -> E4 -> PM | uncommitted | GrafanaDataWriter leader election + caller handles non-leader skip |
| OS-002 | P1 | E | fixed | PM -> E3/PA -> E1/E1a/TW -> E2 -> E4 -> PM | uncommitted | DB reset confirm code fingerprinted to DSN/env; wrapper cannot auto-confirm |
| OS-003 | P2 | E | fixed | PM -> E3/PA -> E1/E1a/TW -> E2 -> E4 -> PM | uncommitted | lifecycle stop/restart scripts use PID/cwd/command validation instead of broad `pkill -f` kills |
| OS-004 | P2 | E | fixed | PM -> E3/PA -> E1/E1a/TW -> E2 -> E4 -> PM | uncommitted | maintenance flag cleanup trap on EXIT/INT/TERM in fresh/clean scripts |
| OS-005 | P2 | E | fixed | PM -> E3/PA -> E1/E1a/TW -> E2 -> E4 -> PM | uncommitted | launchd preflight script + runbook requires preflight-before-load |
| OS-006 | P2 | E | fixed | PM -> E3/PA -> E1/E1a/TW -> E2 -> E4 -> PM | uncommitted | `trading_admin` least-privilege role + fixed SQL heredoc + safe password binding via psql var |
| OS-007 | P3 | E | fixed | PM -> E3/PA -> E1/E1a/TW -> E2 -> E4 -> PM | uncommitted | Telegram JSON encoded via `jq`; curl tokenized URL removed from argv |
| DAPI-007 | P2 | E | fixed | PM -> E3/PA -> E1/E1a/TW -> E2 -> E4 -> PM | uncommitted | `/api/v1/system/scheduled-restart` disabled (410) and redirected to service manager |
| MLM-001 | P1 | F | fixed | PM(local; dirty-collision preserved) -> QC/MIT/PA local review -> E4 tests -> PM | uncommitted | real feature-definition hash + ONNX definition-hash rejection test |
| MLM-002 | P1 | F | fixed | PM(local; dirty-collision preserved) -> QC/MIT/PA local review -> E4 tests -> PM | uncommitted | model registry trio canary transition + model_info incomplete-trio guard tests |
| MLM-003 | P1 | F | fixed | PM(local; dirty-collision preserved) -> QC/MIT/PA local review -> E4 tests -> PM | uncommitted | ETL row-level schema/hash filters + malformed feature JSON reject tests |
| MLM-004 | P1 | F | fixed | PM(local; dirty-collision preserved) -> QC/MIT/PA local review -> E4 tests -> PM | uncommitted | label backfill requires full close quantity before final label |
| MLM-005 | P1 | F | fixed | PM(local; dirty-collision preserved) -> QC/MIT/PA local review -> E4 tests -> PM | uncommitted | LinUCB arm-space/SQL/runtime state load tests |
| SADF-001 | P1 | F | fixed | PM(local; dirty-collision preserved) -> QC/MIT/PA local review -> E4 tests -> PM | uncommitted | Teacher commands route to Demo target; disabled Paper rejects oneshot commands |
| SADF-004 | P2 | F | fixed | PM(local; dirty-collision preserved) -> QC/MIT/PA local review -> E4 tests -> PM | uncommitted | decision payload marks LinUCB as signal observation only |
| SADF-005 | P2 | F | fixed | PM(local; dirty-collision preserved) -> QC/MIT/PA local review -> E4 tests -> PM | uncommitted | `boost_arm` returns unsupported/invalid directive instead of applied |
| SADF-006 | P3 | F | fixed | PM(local; dirty-collision preserved) -> QC/MIT/PA local review -> E4 tests -> PM | uncommitted | Strategist Live metrics path release-mode fail-fast guard |
| LP-003 | P3 | F | fixed | PM(local; dirty-collision preserved) -> QC/MIT/PA local review -> E4 tests -> PM | uncommitted | Paper auto-start requires `OPENCLAW_ENABLE_PAPER=1`; stale runbook path retired |

## Preflight Notes

- Linux `trade-core` repo state at Batch A start: `main...origin/main`, clean.
- Linux watchdog at Batch A start: `engine_alive=true`, `demo/live=true`, `paper=false`. This runtime/docs drift must be handled before deploy or restart.
- Mac worktree is dirty from prior Codex/user work. Batch A implementation must preserve unrelated edits and avoid broad rewrites.

## Batch A Verification Notes

- Python: `/tmp/openclaw-batch-a-venv/bin/python -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_live_authorization_signing.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_shadow_toggle_api.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_promote_api.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_live_auth_recheck_trigger.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_live_gate_fallback.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_operator_live_flatten_boundary.py` -> 69 passed.
- Follow-up reassessment: `test_session_stop_channel_unavailable_returns_409` fixture now carries `operator` role + `live:trade` scope required by Batch B hardening; Batch A targeted suite rerun -> 69 passed.
- Rust release checks (E4): `cargo test --release -p openclaw_engine live_authorization --lib` -> 18 passed; `tick_pipeline::tests::dual_rail_dispatch --lib` -> 13 passed; `strategist_scheduler::tests --lib` -> 26 passed; `main_boot_tasks::edge_reload_tests --bin openclaw-engine` -> 13 passed; `live_auth_watcher --bin openclaw-engine` -> 10 passed.
- Static hygiene: `python3 -m py_compile` on touched Python files passed; `git diff --check` passed.
- E2 adversarial review initially blocked on Python v1 auth verifier drift; follow-up review accepted after `executor_routes.py` and auth signing tests were upgraded to schema v2.
- No deploy/restart performed. Linux `trade-core` runtime drift from preflight remains out of scope for Batch A implementation.

## Batch B Verification Notes

- Python: `/tmp/openclaw-batch-a-venv/bin/python -m pytest -p no:cacheprovider program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_b_security_auth.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_ai_budget_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_reset_drawdown_route.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_shadow_toggle_api.py -q` -> 47 passed.
- Python syntax: `py_compile` on touched API/test files passed.
- Shell/plist/compose: `bash -n` on modified operator scripts passed; `plutil -lint` on modified launchd plists passed; `docker-compose config` passed for control API and monitoring with dummy secrets.
- Rust: `cargo check -p openclaw_engine --manifest-path rust/Cargo.toml` passed with pre-existing unused/dead-code warnings.
- Static hygiene: `git diff --check` passed; targeted `rg` found no Batch B residuals for password-bearing `psql "$DSN"`, tokenized Telegram URL, `OPENCLAW_API_TOKEN='change-me'`, `3000:3000`, proxy cookie/auth forwarding, or long-lived `OPENCLAW_IPC_SECRET="${...}"` launch paths.
- `cargo fmt --all --check` remains blocked by broad pre-existing Rust formatting drift outside the Batch B touch set; no formatting rewrite was performed.
- No deploy/restart performed.

## Batch C Verification Notes

- Rust formatting: `rustfmt --edition 2021` on touched Rust files passed.
- Rust compile: `cargo check -p openclaw_engine --manifest-path rust/Cargo.toml` passed with pre-existing unused/dead-code warnings.
- Rust targeted tests: `bybit_private_ws` -> 31 passed; `pending_registration_order_type_tests` -> 8 passed; `emit_close_fill` -> 13 passed; `batch_insert` -> 10 passed; `migrations` -> 15 passed.
- Python syntax: `/tmp/openclaw-batch-a-venv/bin/python -m py_compile` on `db_pool.py`, `strategy_ai_routes.py`, `live_session_account_routes.py`, and `live_session_endpoints.py` passed.
- Python targeted tests: `/tmp/openclaw-batch-a-venv/bin/python -m pytest -p no:cacheprovider program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_db_pool_connection_reset.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_session_stop_cancel_verify.py -q --tb=short` -> 14 passed, 11 existing warnings.
- E4 initially found three 401s in direct handler tests after Batch B auth hardening; PM fixed the tests to pass authenticated actors with `operator` role and required scopes, then reran green.
- No deploy/restart performed.

## Batch D Verification Notes

- Rust compile: `cargo check -p openclaw_engine --manifest-path rust/Cargo.toml` -> passed with pre-existing unused/dead-code warnings.
- Batch D static guards: `PYTHONDONTWRITEBYTECODE=1 /tmp/openclaw-batch-a-venv/bin/python -m pytest -p no:cacheprovider program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_d_risk_fail_closed.py -q --tb=short` -> 8 passed.
- Follow-up reassessment fixed two real gaps:
  - `RC-005`: opposite-side reducing intents are capped before Guardian/risk checks to existing position qty; exchange dispatch marks those orders close/reduce-only and skips proactive mirror insertion.
  - `RC-006`: legacy `update_risk_config` returns JSON-RPC success only after event-consumer application ack (`queued=false`, `applied=true`), with send/apply/timeout failures surfaced as errors.
- Rust targeted tests:
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml status_risk_snapshot_preserves_active_cooldown_and_kill_switch --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_load_unified_configs_missing_demo_live_is_error --bin openclaw-engine` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_governor_reduced_blocks_new_entries --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_governor_cautious_scales_new_entry_qty --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_conf_scale_not_partially_applied_when_typed_validation_fails --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_e4_5_handle_update_risk_config_send_failure_returns_internal_error --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_load_strategy_params_missing_file_demo_is_fail_closed_inactive --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_load_strategy_params_invalid_toml_live_is_fail_closed_inactive --lib` -> 1 passed.
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_close_attempt_timeout_constant_is_500ms --lib` -> 1 passed.
- Follow-up tests: `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_governor_ --lib` -> 4 passed; `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml test_e4_5_handle_update_risk_config --lib` -> 3 passed; `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml intent_processor::tests:: --lib` -> 86 passed; `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml --lib` -> 2355 passed.
- No deploy/restart performed.

## Batch E Verification Notes

- Shell syntax: `bash -n helper_scripts/clean_restart.sh helper_scripts/fresh_start.sh helper_scripts/restart_all.sh helper_scripts/stop_all.sh helper_scripts/cron_daily_report.sh helper_scripts/cron_observer_cycle.sh helper_scripts/db/counterfactual_daily_cron.sh helper_scripts/db/passive_wait_healthcheck_cron.sh helper_scripts/deploy/launchd_preflight.sh helper_scripts/mac_bootstrap_db.sh` -> passed.
- Python syntax: `/tmp/openclaw-batch-a-venv/bin/python -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_legacy_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/evolution_auto_scheduler.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/experiment_ledger.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_wiring.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/grafana_data_writer.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py helper_scripts/db/fresh_start_reset.py` -> passed.
- Batch E static guards: `PYTHONDONTWRITEBYTECODE=1 /tmp/openclaw-batch-a-venv/bin/python -m pytest -p no:cacheprovider program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_e_runtime_ownership.py -q --tb=short` -> 10 passed.
- Cross-batch regression check: `PYTHONDONTWRITEBYTECODE=1 /tmp/openclaw-batch-a-venv/bin/python -m pytest -p no:cacheprovider program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_b_security_auth.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_e_runtime_ownership.py -q --tb=short` -> 20 passed.
- Follow-up reassessment fixed two real gaps:
  - `OS-003`: `restart_all.sh`, `stop_all.sh`, `clean_restart.sh`, and `fresh_start.sh` now signal only validated engine PIDs whose cwd/command belong to this repo.
  - `OS-006`: `mac_bootstrap_db.sh` SQL heredoc is properly closed; shell fragments are no longer written into the temporary SQL file.
- Follow-up static checks: no `pkill -f`, `ENGINE_CMD_FRAGMENT`, or nested `cat >> "$TMP_SQL"` remains in lifecycle/bootstrap scripts; Batch D+E static guard suite -> 18 passed.
- `cron_daily_report.sh` follow-up fix: lock cleanup now runs even when env validation exits early, preventing stale lock false-positive overlap.
- No deploy/restart performed.

## A-E Reassessment Notes

- Previous D/E "open tracking" finding is stale: tracking and sign-off docs exist for A/B/C/D/E. Batch F was subsequently closed locally in the Batch F sign-off pass.
- Previous A red test was real but test-fixture drift, not production handler failure; fixed and rerun green.
- Previous RC-005, RC-006, OS-003, and OS-006 gaps were real; all are now patched and covered by targeted/static tests.
- Aggregate reassessment verification: A-E Python targeted suite -> 128 passed, 22 existing warnings; Rust full lib suite -> 2355 passed; `cargo check -p openclaw_engine --manifest-path rust/Cargo.toml` passed with existing warnings; `cargo build --release -p openclaw_engine --manifest-path rust/Cargo.toml` passed with existing warnings; `git diff --check` passed.

## Batch F Verification Notes

- Python syntax: `python3 -m py_compile program_code/ml_training/parquet_etl.py program_code/ml_training/quantile_trainer.py program_code/ml_training/quantile_reports.py program_code/ml_training/run_training_pipeline.py program_code/ml_training/model_registry.py program_code/ml_training/edge_label_backfill.py program_code/ml_training/linucb_trainer.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/ml_routes.py` -> passed.
- Shell syntax: `bash -n helper_scripts/start_paper_trading.sh` -> passed.
- Rust compile: `cargo check -p openclaw_engine` from `rust/` -> passed with existing warnings.
- Python targeted suite with bundled runtime: `pytest -q program_code/ml_training/tests/test_parquet_etl.py program_code/ml_training/tests/test_quantile_trainer.py program_code/ml_training/tests/test_quantile_reports.py program_code/ml_training/tests/test_model_registry.py program_code/ml_training/tests/test_edge_label_backfill.py program_code/ml_training/tests/test_linucb_trainer.py` -> 78 passed, 7 skipped.
- Rust targeted tests: Teacher IPC tests -> 6 passed; `boost_arm` tests -> 3 passed; LinUCB runtime tests -> 11 passed; decision-context tests -> 6 passed; edge feature tests -> 20 passed; ORT metadata drift test with `edge_predictor_ort` feature -> 1 passed.
- Residual QA gaps before production release: no deploy/restart/commit/push; no live Postgres integration run for model registry unless `OPENCLAW_DATABASE_URL` is supplied; no real ONNX artifact end-to-end load beyond metadata validation; LinUCB state load was covered by helper/unit tests, not a live boot smoke.

## Batch A-F Release Gate Reverification Notes

- Full local Rust package gate: `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml` -> passed, including doc tests.
- Local release rebuild: `cargo build --release -p openclaw_engine --manifest-path rust/Cargo.toml` -> passed with existing unused/dead-code warnings.
- Full Control API suite: `/tmp/openclaw-batch-a-venv/bin/python -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests --tb=short` -> 3182 passed, 5 skipped.
- Full ML suite: `/tmp/openclaw-ml-verify-venv/bin/python -m pytest -q program_code/ml_training/tests --tb=short` -> 317 passed, 17 skipped.
- Static gates: `git diff --check` passed; `bash -n` over shell scripts under `helper_scripts` and `control_api_v1` passed; `py_compile` over 55 changed/untracked Python files passed.
- Ledger integrity check: 62 findings, 62 unique IDs, all status `fixed`.
- Reverification fixes applied: control API test auth/state drift, Rust doctest prose drift, ML pooled-training monkeypatch path, and missing `psycopg2-binary` in `requirements-ml.txt` for legacy training readers.
- Release boundary remains: no commit/push/deploy/restart was performed. Read-only `trade-core` check showed remote HEAD `890e578`, branch `main`, dirty count 0. Production release still requires target-runtime rebuild/restart and smoke tests.
- Formatting note: `cargo fmt --all --check --manifest-path rust/Cargo.toml` still fails on broad repo-wide formatting drift; no auto-format was run because the worktree is dirty across many parallel-session files.
