# Entry Points and Services

Created: 2026-04-28

## Summary

- Entry-point records: 238
- api_startup_task: 5
- docker_service: 6
- fastapi_app: 1
- fastapi_compat_app: 1
- fastapi_legacy_app: 1
- fastapi_router: 23
- launchd_service: 4
- python_cli: 162
- rust_binary: 1
- shell_script: 34

## Mutation Risk Buckets

- api_mutating_or_sensitive: 9
- api_read_or_mixed: 14
- db_mutating: 29
- db_mutating_or_db_sensitive: 4
- db_or_model_artifact_mutating: 5
- db_schema_mutating: 4
- external_api_sensitive: 6
- external_gateway_service: 1
- ipc_service: 1
- monitoring_or_alerting: 1
- readonly_external_api: 10
- readonly_or_observer: 1
- scheduled_db_or_file_writer: 1
- scheduled_state_or_db_touch: 5
- service_mutating: 10
- service_or_observer: 5
- state_mutating_or_live_capable: 4
- trading_config_mutating: 3
- trading_state_mutating: 1
- unknown_until_review: 69
- validation_or_readonly: 55

## Service-Level Entry Points

| Kind | Path | Command / target | Role | Risk |
| --- | --- | --- | --- | --- |
| api_startup_task | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ai_service.py` | `create_ai_service_listener(); listener.start()` | AIServiceListener | ipc_service |
| api_startup_task | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py` | `start_scheduler() at API startup` | EdgeEstimatorScheduler | scheduled_db_or_file_writer |
| api_startup_task | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/evolution_auto_scheduler.py` | `start_scheduler() at API startup` | EvolutionScheduler | scheduled_state_or_db_touch |
| api_startup_task | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py` | `startup auto-seed from TruthSourceRegistry` | ExperimentLedger auto-seed | db_mutating |
| api_startup_task | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_wiring.py` | `asyncio.create_task(...reconciler_alert_monitor())` | reconciler_alert_monitor | monitoring_or_alerting |
| docker_service | `docker_projects/monitoring_services/docker-compose.yml` | `grafana` | Docker Compose service: grafana | service_or_observer |
| docker_service | `docker_projects/trading_services/docker-compose.yml` | `audit_logger` | Docker Compose service: audit_logger | service_or_observer |
| docker_service | `docker_projects/trading_services/docker-compose.yml` | `binance_connector` | Docker Compose service: binance_connector | service_or_observer |
| docker_service | `docker_projects/trading_services/docker-compose.yml` | `bybit_connector` | Docker Compose service: bybit_connector | service_or_observer |
| docker_service | `docker_projects/trading_services/docker-compose.yml` | `pretrade_risk_gate` | Docker Compose service: pretrade_risk_gate | service_or_observer |
| docker_service | `docker_projects/trading_services/openclaw_bybit_control_api_v1/docker-compose.yml` | `openclaw_bybit_control_api_v1` | Docker Compose service: openclaw_bybit_control_api_v1 | service_mutating |
| fastapi_app | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py` | `uvicorn app.main:app --host 0.0.0.0 --port 8000` | Control API v1 HTTP service | service_mutating |
| fastapi_compat_app | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main_snapshot_stable.py` | `uvicorn app.main_snapshot_stable:app` | Compatibility API entry | service_mutating |
| fastapi_legacy_app | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main_legacy.py` | `uvicorn app.main_legacy:app` | Legacy Control API app | service_mutating |
| launchd_service | `helper_scripts/deploy/com.openclaw.engine-watchdog.plist` | `/usr/bin/env python3 __BASE__/helper_scripts/canary/engine_watchdog.py --data-dir __HOME__/.openclaw_runtime --stale-threshold 45 --grace-period 120 --poll-interval 1` | launchd service | service_mutating |
| launchd_service | `helper_scripts/deploy/com.openclaw.engine.plist` | `__BASE__/rust/target/release/openclaw-engine` | launchd service | service_mutating |
| launchd_service | `helper_scripts/deploy/com.openclaw.gateway.plist` | `/usr/local/bin/node __HOME__/.npm-global/lib/node_modules/openclaw/dist/entry.js gateway --port 18789` | launchd service | external_gateway_service |
| launchd_service | `helper_scripts/deploy/com.openclaw.trading-api.plist` | `__BASE__/program_code/exchange_connectors/bybit_connector/control_api_v1/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000` | launchd service | service_mutating |
| rust_binary | `rust/openclaw_engine/src/main.rs` | `cargo run --release -p openclaw_engine / rust/target/release/openclaw-engine` | Rust trading engine | service_mutating |

## High-Risk Operator / CLI Entry Points

These are not confirmed findings. They are first-review targets because they can start/stop services, mutate DB state, call exchange APIs, or alter trading configuration.

| Path | Role | Risk | Evidence |
| --- | --- | --- | --- |
| `helper_scripts/canary/canary_comparator.py` | data writer CLI | db_mutating | __main__ |
| `helper_scripts/canary/g2_03_bind_helper.py` | data writer CLI | db_mutating | __main__ |
| `helper_scripts/db/canary_promote_runner.py` | data writer CLI | db_mutating | __main__ |
| `helper_scripts/db/counterfactual_exit_replay.py` | data writer CLI | db_mutating | __main__ |
| `helper_scripts/db/passive_wait_healthcheck.py` | data writer CLI | db_mutating | __main__ |
| `helper_scripts/db/passive_wait_healthcheck/runner.py` | data writer CLI | db_mutating | __main__ |
| `helper_scripts/phase4/dl3_go_no_go.py` | data writer CLI | db_mutating | __main__ |
| `helper_scripts/phase4/weekly_report.py` | data writer CLI | db_mutating | __main__ |
| `program_code/ai_agents/bybit_thought_gate/bybit_ai_invocation_attempt_builder.py` | data writer CLI | db_mutating | __main__ |
| `program_code/ai_agents/bybit_thought_gate/bybit_ai_prompt_prep_builder.py` | data writer CLI | db_mutating | __main__ |
| `program_code/audit/counterfactual_exit_audit.py` | data writer CLI | db_mutating | __main__ |
| `program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_decision_packet_to_postgres.py` | data writer CLI | db_mutating | __main__ |
| `program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_load_ws_jsonl_to_postgres.py` | data writer CLI | db_mutating | __main__ |
| `program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_normalize_latest_snapshot_to_postgres.py` | data writer CLI | db_mutating | __main__ |
| `program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_public_connectivity_status_writer.py` | data writer CLI | db_mutating | __main__ |
| `program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_snapshot_to_postgres.py` | data writer CLI | db_mutating | __main__ |
| `program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/bybit_build_decision_packet.py` | data writer CLI | db_mutating | __main__ |
| `program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/bybit_build_observer_verdict.py` | data writer CLI | db_mutating | __main__ |
| `program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/bybit_failure_policy_builder.py` | data writer CLI | db_mutating | __main__ |
| `program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/bybit_next_phase_handoff.py` | data writer CLI | db_mutating | __main__ |
| `program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/bybit_observer_pipeline.py` | data writer CLI | db_mutating | __main__ |
| `program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/bybit_observer_verdict_to_postgres.py` | data writer CLI | db_mutating | __main__ |
| `program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/bybit_readonly_audit.py` | data writer CLI | db_mutating | __main__ |
| `program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/bybit_readonly_status_writer.py` | data writer CLI | db_mutating | __main__ |
| `program_code/market_data_processor/bybit_business_events/bybit_business_event_fixture_pack_builder.py` | data writer CLI | db_mutating | __main__ |
| `program_code/ml_training/edge_cluster_analysis.py` | data writer CLI | db_mutating | __main__ |
| `program_code/ml_training/edge_label_backfill.py` | data writer CLI | db_mutating | __main__ |
| `program_code/ml_training/james_stein_estimator.py` | data writer CLI | db_mutating | __main__ |
| `helper_scripts/db/audit_migrations.py` | database/operator CLI | db_mutating_or_db_sensitive | __main__ |
| `helper_scripts/db/check_migration_status.py` | database/operator CLI | db_mutating_or_db_sensitive | __main__ |
| `helper_scripts/db/passive_wait_healthcheck/__main__.py` | database/operator CLI | db_mutating_or_db_sensitive | __main__ |
| `helper_scripts/db/phase1a_c_readiness.py` | database/operator CLI | db_mutating_or_db_sensitive | __main__ |
| `program_code/ai_agents/bybit_thought_gate/bybit_model_router_decision.py` | ML/training CLI | db_or_model_artifact_mutating | __main__ |
| `program_code/ai_agents/bybit_thought_gate/bybit_model_router_policy.py` | ML/training CLI | db_or_model_artifact_mutating | __main__ |
| `program_code/ai_agents/bybit_thought_gate/bybit_model_router_runtime.py` | ML/training CLI | db_or_model_artifact_mutating | __main__ |
| `program_code/ml_training/realized_edge_stats.py` | ML/training CLI | db_or_model_artifact_mutating | __main__ |
| `program_code/ml_training/run_training_pipeline.py` | ML/training CLI | db_or_model_artifact_mutating | __main__ |
| `helper_scripts/db/deploy_V017.sh` | database deployment script | db_schema_mutating | psql/migration wrapper |
| `helper_scripts/db/deploy_V018.sh` | database deployment script | db_schema_mutating | psql/migration wrapper |
| `helper_scripts/linux_bootstrap_db.sh` | database deployment script | db_schema_mutating | psql/migration wrapper |
| `helper_scripts/mac_bootstrap_db.sh` | database deployment script | db_schema_mutating | psql/migration wrapper |
| `program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_private_account_check.py` | exchange/private check CLI | external_api_sensitive | __main__ |
| `program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_private_execution_history_check.py` | exchange/private check CLI | external_api_sensitive | __main__ |
| `program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_private_order_history_check.py` | exchange/private check CLI | external_api_sensitive | __main__ |
| `program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_private_positions_check.py` | exchange/private check CLI | external_api_sensitive | __main__ |
| `program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_private_readonly_precheck.py` | exchange/private check CLI | external_api_sensitive | __main__ |
| `program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_private_rest_preflight_guard.py` | exchange/private check CLI | external_api_sensitive | __main__ |
| `helper_scripts/cron_daily_report.sh` | cron wrapper | scheduled_state_or_db_touch | crontab documented |
| `helper_scripts/cron_observer_cycle.sh` | cron wrapper | scheduled_state_or_db_touch | crontab documented |
| `helper_scripts/db/counterfactual_daily_cron.sh` | cron wrapper | scheduled_state_or_db_touch | crontab documented |
| `helper_scripts/db/passive_wait_healthcheck_cron.sh` | cron wrapper | scheduled_state_or_db_touch | crontab documented |
| `helper_scripts/restart_all.sh` | service supervisor script | service_mutating | starts/stops engine and API |
| `helper_scripts/stop_all.sh` | service supervisor script | service_mutating | stops engine/API, writes maintenance flag |
| `helper_scripts/clean_restart.sh` | destructive reset script | state_mutating_or_live_capable | kills services, may flatten exchange state, truncates DB |
| `helper_scripts/clean_restart_flatten.py` | operator destructive CLI | state_mutating_or_live_capable | __main__ |
| `helper_scripts/db/fresh_start_reset.py` | operator destructive CLI | state_mutating_or_live_capable | __main__ |
| `helper_scripts/fresh_start.sh` | destructive reset script | state_mutating_or_live_capable | kills services, may flatten exchange state, truncates DB |
| `helper_scripts/operator/edge_p2_flip.sh` | operator IPC script | trading_config_mutating | sends IPC/config commands |
| `helper_scripts/operator/edge_p2_revert.sh` | operator IPC script | trading_config_mutating | sends IPC/config commands |
| `helper_scripts/operator/g2_03_bind_ma_sltp.sh` | operator IPC script | trading_config_mutating | sends IPC/config commands |
| `helper_scripts/start_paper_trading.sh` | paper trading activator | trading_state_mutating | POSTs paper session/feed/strategy endpoints |
| `helper_scripts/canary/edge_p2_flip_dry_run.py` | utility CLI | unknown_until_review | __main__ |
| `helper_scripts/canary/engine_watchdog.py` | utility CLI | unknown_until_review | __main__ |
| `helper_scripts/canary/replay_runner.py` | utility CLI | unknown_until_review | __main__ |
| `helper_scripts/canary/rollback_drill.sh` | operator shell script | unknown_until_review | shell entry point |
| `helper_scripts/db/cleanup_v026_partial_state.sh` | operator shell script | unknown_until_review | shell entry point |
| `helper_scripts/db/passive_wait_healthcheck.sh` | operator shell script | unknown_until_review | shell entry point |
| `helper_scripts/golden_dataset_gen.py` | utility CLI | unknown_until_review | __main__ |
| `helper_scripts/mac_bootstrap.sh` | operator shell script | unknown_until_review | shell entry point |
| `helper_scripts/maintenance_scripts/bybit_connector/_bybit_latest_wrapper.py` | utility CLI | unknown_until_review | __main__ |
| `helper_scripts/maintenance_scripts/bybit_connector/lib_trading_env.sh` | operator shell script | unknown_until_review | shell entry point |
| `helper_scripts/maintenance_scripts/bybit_connector/repair_i10_stage_source_aliases.py` | utility CLI | unknown_until_review | __main__ |
| `helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_decision_lease_recheck.sh` | operator shell script | unknown_until_review | shell entry point |
| `helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_h_chain_recheck.sh` | operator shell script | unknown_until_review | shell entry point |
| `helper_scripts/maintenance_scripts/bybit_connector/run_with_trading_env.sh` | operator shell script | unknown_until_review | shell entry point |
| `helper_scripts/maintenance_scripts/prune_dated_files.sh` | operator shell script | unknown_until_review | shell entry point |
| `helper_scripts/research/bb_breakout_threshold_sweep.py` | utility CLI | unknown_until_review | __main__ |
| `helper_scripts/research/cost_edge_advisor_observation_report.py` | utility CLI | unknown_until_review | __main__ |
| `helper_scripts/research/exit_features_summary.py` | utility CLI | unknown_until_review | __main__ |
| `helper_scripts/research/exit_threshold_calibrator.py` | utility CLI | unknown_until_review | __main__ |

## FastAPI Router Surface

Router records are listed in `entry_points_manifest.tsv` with kind `fastapi_router`. The default service entry is `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`, launched as `uvicorn app.main:app`.

## Background Tasks Started By API Startup

| Task | Source | Risk | Evidence |
| --- | --- | --- | --- |
| AIServiceListener | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ai_service.py` | ipc_service | main.py create_task and app.state refs |
| EdgeEstimatorScheduler | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py` | scheduled_db_or_file_writer | leader-elected worker only |
| EvolutionScheduler | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/evolution_auto_scheduler.py` | scheduled_state_or_db_touch | main.py imports evolution_auto_scheduler.start_scheduler |
| ExperimentLedger auto-seed | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py` | db_mutating | get_experiment_ledger().auto_seed_from_claims |
| reconciler_alert_monitor | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_wiring.py` | monitoring_or_alerting | main.py create_task |

## Next Review Slice

The next code audit slice should start with live/paper mode separation and service startup boundaries:

- `rust/openclaw_engine/src/main.rs` and its startup modules
- `helper_scripts/restart_all.sh`, `stop_all.sh`, `clean_restart.sh`, `fresh_start.sh`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py` startup hook
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py` and `live_trust_routes.py`
- launchd templates in `helper_scripts/deploy/`

## Caveats

- This is an entry-point map, not a vulnerability report.
- Python CLI detection is based on `if __name__` and path/content heuristics.
- Docker Compose parsing records declared services under the `services:` section only.
- Test files are excluded according to the audit scope.
