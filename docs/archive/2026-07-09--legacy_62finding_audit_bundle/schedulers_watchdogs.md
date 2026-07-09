# Schedulers and Watchdogs Audit

Created: 2026-04-28
Status: complete for this audit slice
Scope: Non-test scheduler, watchdog, background-loop, restart, duplicate-job-protection, shutdown/cancellation, and scheduler-state-persistence paths. Tests are excluded from the reviewed scope.

## Scope

This slice reviewed runtime scheduler and watchdog behavior in:

- Rust engine background tasks, restart/watchdog handoff, Live respawn behavior, cancellation, and ordered shutdown.
- FastAPI startup background tasks, daemon threads, async tasks, multi-worker duplicate protection, and shutdown cleanup.
- launchd service templates for engine, API, and watchdog.
- Watchdog, stop, restart, clean restart, and fresh-start scripts.
- cron/scheduled shell jobs and their Python entry points where the wrapper controls scheduling behavior.
- Scheduler state persistence for the ExperimentLedger and edge-estimator scheduler state.

Tests, generated audit manifests, and unrelated documentation were not used as runtime evidence.

## Reviewed Runtime Paths

- Rust engine orchestration: `rust/openclaw_engine/src/main.rs`, `main_boot_tasks.rs`, `main_pipelines.rs`, `main_shutdown.rs`, `main_watchdog.rs`, `main_ws.rs`, `tasks.rs`, `tasks/supervised_spawn.rs`, `live_auth_watcher.rs`.
- Python API startup and background loops: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`, `ai_service.py`, `ai_service_listener.py`, `edge_estimator_scheduler.py`, `edge_estimator_routes.py`, `evolution_auto_scheduler.py`, `experiment_ledger.py`, `experiment_routes.py`, `paper_trading_wiring.py`, `strategy_wiring.py`, `grafana_data_writer.py`, `executor_config_cache.py`, `ttl_enforcer.py`, `h0_gate.py`, `scout_worker.py`, `strategy_wiring_scanner.py`.
- Watchdog and restart scripts: `helper_scripts/canary/engine_watchdog.py`, `helper_scripts/restart_all.sh`, `helper_scripts/stop_all.sh`, `helper_scripts/fresh_start.sh`, `helper_scripts/clean_restart.sh`.
- Scheduled wrappers: `helper_scripts/cron_observer_cycle.sh`, `helper_scripts/cron_daily_report.sh`, `helper_scripts/db/counterfactual_daily_cron.sh`, `helper_scripts/db/passive_wait_healthcheck_cron.sh`.
- launchd templates: `helper_scripts/deploy/com.openclaw.engine-watchdog.plist`, `helper_scripts/deploy/com.openclaw.engine.plist`, `helper_scripts/deploy/com.openclaw.trading-api.plist`.

## Flow Summary

The Rust engine starts one process with an engine-wide `CancellationToken`, then spawns WS supervision, DB writers, REST pollers, position reconcilers, StrategistScheduler, optional H-state and edge-reload daemons, LiveAuthWatcher, and a tick-stale watchdog. Signal handling fans out cancellation, and `main_shutdown.rs` joins the main WS/IPC/pipeline handles under a timeout.

Live runtime restart behavior is split between a slot abstraction and LiveAuthWatcher. The watcher polls authorization every 5 seconds, supports IPC wakeups, tears Live down immediately on invalid auth, and respawns Live with exponential backoff after auth renewal. The respawn path now creates fresh Live command/event senders and writes them into dynamic slots, but some boot-time background tasks still retain boot-time sender clones.

The Python API startup handler runs once per uvicorn worker. Some services contain cross-worker protection: AIServiceListener probes the Unix socket and only one worker binds it; EdgeEstimatorScheduler uses a host-local `fcntl.flock` leader lock. Other API-started loops are only process-local idempotent and therefore run once per worker under `--workers 4`.

The external engine watchdog runs as a Python process, guarded by a single-instance `fcntl.flock`. It monitors snapshot staleness, honors `engine_maintenance.flag`, applies restart backoff/circuit breaking, and invokes `helper_scripts/restart_all.sh --engine-only` on allowed crash recovery. The stop/fresh-start scripts set the maintenance flag before killing the engine, but clean restart does not.

Cron wrappers run by crontab invoke observer, report, counterfactual replay, and passive-wait healthcheck jobs directly. The wrappers contain no overlap lock, so duplicate invocations are possible if a previous run exceeds its period or hangs.

## Confirmed Findings

### SW-001

Severity: P1
Status: open
Area: Watchdog/restart behavior
Files:

- `helper_scripts/clean_restart.sh`
- `helper_scripts/canary/engine_watchdog.py`
- `helper_scripts/stop_all.sh`
- `helper_scripts/fresh_start.sh`
- `helper_scripts/restart_all.sh`

Summary:

`clean_restart.sh` kills the engine and API, then flattens exchange positions, archives runtime files, and optionally truncates trading tables without first creating `engine_maintenance.flag`. The watchdog treats that flag as the operator-maintenance opt-out and can invoke `restart_all.sh --engine-only` while clean restart is still in its destructive maintenance window.

Evidence:

- `clean_restart.sh:126-141` stops the Rust engine and API without setting any maintenance flag.
- `clean_restart.sh:143-179` then runs exchange flattening, and `clean_restart.sh:182-239` archives runtime files and optionally truncates trading tables before the script's own restart step.
- `clean_restart.sh:270-290` starts engine/API later, so there is a window where the engine is intentionally down.
- `engine_watchdog.py:285-288` skips auto-restart only when `engine_maintenance.flag` exists.
- `engine_watchdog.py:459-463` triggers a restart when the engine is considered crashed and restart is allowed; `engine_watchdog.py:61-64` defines that restart as `bash helper_scripts/restart_all.sh --engine-only`.
- `stop_all.sh:40-47` and `fresh_start.sh:116-118` show the expected pattern: create the maintenance flag before killing the engine. `fresh_start.sh:223-224` clears it immediately before intentional restart.
- `restart_all.sh:221-223` clears the maintenance flag on an explicit restart, which is correct for `restart_all.sh` but does not protect `clean_restart.sh` before its own restart step.

Impact:

If the watchdog is running and `clean_restart.sh` takes longer than the watchdog stale threshold before its explicit restart, the watchdog can restart the engine during flatten/archive/DB reset. That can bring trading logic back while positions are being flattened or runtime state is being moved/truncated, creating a high-risk mixed state.

Trigger:

Run `helper_scripts/clean_restart.sh` while `engine_watchdog.py` is active, and have the flatten/archive/build section exceed the watchdog stale threshold after the initial engine kill.

Recommended fix:

Set `$DATA_DIR/engine_maintenance.flag` at the beginning of clean restart before killing the engine. Use `trap` handling so failures preserve the flag rather than allowing unintended watchdog recovery. Clear the flag only immediately before the script's intentional restart, or call a restart helper that performs the clear in the same step.

Verification:

Static trace only. Add a shell regression that asserts `clean_restart.sh` touches the maintenance flag before `pkill -f openclaw-engine`, and run a dry maintenance scenario with watchdog active to confirm no `RESTART_SUCCESS` or `RESTART_FAILED` watchdog event is emitted before clean restart's own restart step.

### SW-002

Severity: P1
Status: open
Area: Rust Live respawn / stale background command senders
Files:

- `rust/openclaw_engine/src/main.rs`
- `rust/openclaw_engine/src/main_boot_tasks.rs`
- `rust/openclaw_engine/src/main_pipelines.rs`
- `rust/openclaw_engine/src/live_auth_watcher.rs`

Summary:

LiveAuthWatcher respawn creates fresh Live command/event channels and publishes them through dynamic slots, but several boot-time background tasks still hold the original `live_cmd_tx` by value. After Live is torn down and respawned mid-session, those tasks can keep sending to a stale channel instead of the new Live event consumer.

Evidence:

- `main.rs:386-393` mirrors the boot-time Live command sender into `live_cmd_slot` and explicitly notes `LIVE-RECONCILER-STALE-CMD-TX P1 TODO`.
- `main.rs:1006-1016` documents that reconcilers and scheduler capture the boot-time command sender by value and cannot be rotated through the spawner closure.
- `main_boot_tasks.rs:106-117` spawns the Live position reconciler with `tx.clone()` from the boot-time `live_cmd_tx`.
- `main_boot_tasks.rs:306-314` constructs `StrategistScheduler` with `live_cmd_tx.clone()` as the optional promote target.
- `main.rs:1092-1097` passes `live_cmd_tx.clone()` into the edge-estimates reloader daemon.
- `main_pipelines.rs:730-739` documents that the Live respawn spawner builds fresh command/event channels and updates dynamic slots; `main_pipelines.rs:796-807` creates `new_cmd_tx/new_cmd_rx` and writes `new_cmd_tx` into `live_cmd_slot`.
- `live_auth_watcher.rs:725-760` calls the pipeline spawner after a successful Live slot respawn.

Impact:

Dynamic IPC/fan-out paths use the fresh slot sender, but boot-time loops may send to a dropped or no-longer-consumed Live channel after auth revoke/renew. Live position reconciler actions, strategist live promotion commands, or edge-estimate reloads can fail or be silently ineffective until a full engine restart. For risk contraction or live promotion paths this is a P1 restart-integrity issue.

Trigger:

Boot with Live authorized, then revoke or expire Live authorization, then renew it so LiveAuthWatcher performs an in-process Live respawn without a full engine restart. Any later command sent by a boot-time task through its captured `live_cmd_tx` targets the old channel.

Recommended fix:

Replace boot-time `Option<UnboundedSender<PipelineCommand>>` captures for Live with a dynamic command sink that reads `LiveCmdSenderSlot` at send time, or re-create Live-scoped reconcilers/scheduler promotion handles on each Live respawn. Treat send failures as observable errors with counters/alerts, not only local warnings. Add an integration test that respawns Live and proves reconciler/promote/reload commands reach the new receiver.

Verification:

Static trace only. A focused test can create an initial Live sender, rotate `live_cmd_slot` through the spawner path, drop the old receiver, then assert all background Live command paths resolve through the fresh slot.

### SW-003

Severity: P2
Status: open
Area: API startup scheduler / duplicate job protection
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/evolution_auto_scheduler.py`
- `helper_scripts/restart_all.sh`
- `helper_scripts/fresh_start.sh`

Summary:

EvolutionScheduler is started in every API worker and is only process-local idempotent. Under the default `--workers 4` deployment, each worker can spawn its own weekly evolution thread and hourly expiry thread. Unlike EdgeEstimatorScheduler, it has no cross-process leader lock and no shutdown primitive.

Evidence:

- `main.py:399-407` calls `evolution_auto_scheduler.start_scheduler()` during API startup.
- `restart_all.sh:33` defaults `OPENCLAW_API_WORKERS` to `4`, and `restart_all.sh:275-279` starts uvicorn with `--workers "$WORKERS"`.
- `fresh_start.sh:235-241` starts the API with `--workers 4`.
- `evolution_auto_scheduler.py:119-147` protects `start()` with only an in-process `_started` flag and then starts two daemon threads.
- `evolution_auto_scheduler.py:441-477` uses a module-level singleton, which is also process-local under uvicorn workers.
- `evolution_auto_scheduler.py:156-172` and `evolution_auto_scheduler.py:294-304` run `while True` loops; there is no stop event or `shutdown()` method comparable to EdgeEstimatorScheduler.
- EdgeEstimatorScheduler demonstrates the intended cross-worker pattern: `edge_estimator_scheduler.py:548-663` uses `fcntl.flock`, and `edge_estimator_scheduler.py:666-713` returns `None` on non-leader workers.

Impact:

Weekly evolution and hourly expiry can run up to four times per API host. Current default evolution construction passes no truth registry, so the immediate blast radius is mostly duplicate backtest CPU and duplicate ledger expiry attempts, but the scheduler accepts injected `truth_registry` and the engine can register claims when configured. Future dependency injection or route reuse could turn the same duplicate execution into duplicate learning writes.

Trigger:

Start the API through `restart_all.sh` or `fresh_start.sh` with `OPENCLAW_API_WORKERS` unset or greater than `1`, then wait for an expiry/evolution interval or call the scheduler in each worker.

Recommended fix:

Use the same host-local leader election pattern as EdgeEstimatorScheduler, or make EvolutionScheduler explicitly single-worker via deployment configuration. Add a stop event, retain thread handles, expose `shutdown()`, and call it from FastAPI shutdown. Prefer `Event.wait(timeout)` over `time.sleep()` chunks so shutdown is bounded.

Verification:

Static trace only. Add a multi-process startup test or smoke script that starts four worker processes and asserts only one evolution/expiry scheduler thread logs as leader. Add unit coverage for `shutdown()` and for non-leader no-op behavior.

### SW-004

Severity: P2
Status: open
Area: Scheduler state persistence
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/evolution_auto_scheduler.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/experiment_ledger.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/experiment_routes.py`

Summary:

The hourly expiry scheduler marks stale hypotheses as `EXPIRED`, but `ExperimentLedger.expire_stale_hypotheses()` does not schedule a snapshot save. Expired state can be lost across API restart unless another unrelated ledger mutation schedules a debounced save later.

Evidence:

- `evolution_auto_scheduler.py:294-304` runs the hourly expiry loop and calls `_run_expiry_cycle()`.
- `evolution_auto_scheduler.py:314-324` gets the ledger and calls `ledger.expire_stale_hypotheses()`.
- `experiment_ledger.py:602-630` mutates hypothesis status and `concluded_at_ms` for expired hypotheses, then returns `expired_count` without calling `_schedule_debounced_save()`.
- Other ledger mutations do persist: `experiment_ledger.py:331-333` schedules a save after `propose_hypothesis()`, and `experiment_ledger.py:492-501` plus `experiment_ledger.py:506-509` schedule saves after observation-driven state changes.
- `experiment_ledger.py:919-951` implements the debounced save scheduler.
- `experiment_routes.py:75-99` restores ledger state from the persisted snapshot on first access, so unsaved expiry changes disappear on process restart.

Impact:

Expired hypotheses can reload as `PENDING` or `RUNNING`, causing the learning/experiment layer to keep considering stale claims. In a multi-worker deployment this also combines with SW-003, because multiple expiry workers can mutate the same process-local view without durable convergence.

Trigger:

A hypothesis reaches its TTL, the hourly expiry loop marks it expired, and the API process exits or restarts before another propose/observation mutation causes a debounced save.

Recommended fix:

Have `expire_stale_hypotheses()` schedule a debounced save when `expired_count > 0`, preferably outside the ledger lock. Alternatively return expired IDs and let the scheduler request a save. Add a regression that expires a hypothesis, waits for the debounce write, reloads a new ledger instance, and asserts the status remains `EXPIRED`.

Verification:

Static trace only. No runtime persistence test was executed in this audit.

### SW-005

Severity: P2
Status: open
Area: API startup monitoring / duplicate alert protection
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_wiring.py`
- `helper_scripts/restart_all.sh`

Summary:

`reconciler_alert_monitor()` is scheduled once per API worker and deduplicates only in local memory. In the default four-worker deployment, a single governor-tier transition can generate duplicate alerts from every worker.

Evidence:

- `main.py:442-455` calls `asyncio.create_task(_recon_monitor(), name="reconciler-alert-monitor")` during startup.
- `restart_all.sh:33` defaults to four API workers, and `restart_all.sh:275-279` launches uvicorn with that worker count.
- `paper_trading_wiring.py:425-440` defines the 30-second polling monitor.
- `paper_trading_wiring.py:456-458` stores `prev_tier` as a local coroutine variable, so each worker has an independent dedup baseline.
- `paper_trading_wiring.py:460-484` loops forever and skips only if the local worker's `tier == prev_tier`.
- `paper_trading_wiring.py:521-527` sends the alert through `ALERT_ROUTER.alert_system`.
- `main.py:515-528` shuts down only `AIServiceListener`; the reconciler monitor task handle is not stored or explicitly cancelled.

Impact:

Risk-tier changes can produce N duplicate Telegram/system alerts for N API workers. This reduces signal quality during incidents and can obscure whether the risk tier is flapping or only duplicated by worker topology. The missing task handle also leaves shutdown behavior to event-loop teardown instead of explicit cancellation.

Trigger:

Run API with multiple workers and cause any governor tier transition after all workers have observed an initial `prev_tier`.

Recommended fix:

Elect one alert-monitor leader per host, or move dedup into a shared store keyed by `(event_type, tier, transition_version/time_bucket)`. Store the created task handle in `app.state` and cancel/await it in FastAPI shutdown.

Verification:

Static trace only. Add a multi-worker smoke test or a dependency-injected unit test with two monitor instances observing the same tier sequence and assert only one alert is emitted.

### SW-006

Severity: P2
Status: open
Area: Cron/scheduled wrapper duplicate execution
Files:

- `helper_scripts/cron_observer_cycle.sh`
- `helper_scripts/cron_daily_report.sh`
- `helper_scripts/db/counterfactual_daily_cron.sh`
- `helper_scripts/db/passive_wait_healthcheck_cron.sh`

Summary:

The cron wrappers run scheduled jobs directly without `flock`, lockfile, pidfile, or equivalent overlap protection. If one run exceeds its schedule interval or hangs, cron can start a second instance that writes the same logs, JSON snapshots, reports, or Telegram notification path concurrently.

Evidence:

- `cron_observer_cycle.sh:5` documents a `*/5 * * * *` schedule; `cron_observer_cycle.sh:48` runs the observer pipeline and `cron_observer_cycle.sh:59-60` runs the runtime snapshot bridge directly.
- `cron_daily_report.sh:16-20` documents a daily crontab entry; `cron_daily_report.sh:122-125` sends the Telegram message directly.
- `counterfactual_daily_cron.sh:35-37` documents the daily schedule; `counterfactual_daily_cron.sh:109-117` runs `counterfactual_exit_replay.py` and appends the same log.
- `passive_wait_healthcheck_cron.sh:17-18` documents a six-hour schedule; `passive_wait_healthcheck_cron.sh:31-39` runs the healthcheck and appends the same log file.
- A search for `flock`, `lockfile`, `pidfile`, `pgrep`, or a lock-directory pattern in these wrappers found no overlap guard; the lock hits in the reviewed script set are in stop/watchdog scripts, not these cron wrappers.

Impact:

The five-minute observer path is most exposed: overlapping observer and bridge runs can race on latest-cycle/runtime snapshot files and append interleaved logs. The daily and six-hour jobs can duplicate Telegram reports or health/audit trend writes if the prior invocation stalls.

Trigger:

Any scheduled wrapper takes longer than its cron interval, hangs on network/DB/API I/O, or is manually invoked while cron is already running it.

Recommended fix:

Add per-job nonblocking locks under `$OPENCLAW_DATA_DIR/locks` or another operator-configurable runtime directory, for example `flock -n "$lock" ...`. Emit an explicit skipped-run log line and choose exit semantics intentionally per monitor. For observer-cycle, include stale-lock/timeout handling because the period is only five minutes.

Verification:

Static trace only. Add a shell-level concurrency check that starts one wrapper with a held lock and verifies a second invocation exits through the skip path without running the underlying Python command.

### SW-007

Severity: P3
Status: open
Area: API startup telemetry loop / duplicate data writer
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/grafana_data_writer.py`
- `helper_scripts/restart_all.sh`

Summary:

`GrafanaDataWriter` starts during `strategy_wiring` import in every API worker. Its `start()` method is idempotent only for that instance/process, and the writer inserts legacy telemetry rows every 30 seconds without a cross-worker leader lock or idempotent DB key.

Evidence:

- `strategy_wiring.py:615-627` constructs `GrafanaDataWriter` and immediately calls `GRAFANA_WRITER.start()`.
- `grafana_data_writer.py:119-146` starts one daemon thread per instance and loops every configured interval, defaulting to 30 seconds from `grafana_data_writer.py:101-103`.
- `grafana_data_writer.py:221-229` inserts into `paper_pnl_snapshots_legacy` with no `ON CONFLICT` or unique-key guard.
- `grafana_data_writer.py:263-270` inserts into `system_health_legacy` with no `ON CONFLICT` or unique-key guard.
- `restart_all.sh:33` defaults the API to four workers, and `restart_all.sh:275-279` starts uvicorn with `--workers "$WORKERS"`.

Impact:

Dashboard tables can receive one row per API worker per interval, inflating storage and distorting Grafana panels that assume one telemetry sample per 30-second bucket. This does not directly alter trading state, but it degrades observability and alert interpretation.

Trigger:

Run the API with multiple workers while the Rust snapshot exists and the legacy telemetry tables are reachable.

Recommended fix:

Make the writer leader-elected like EdgeEstimatorScheduler, disable it on non-leader workers, or move the telemetry write to a single service. Add database idempotency for `(time_bucket, component/session)` if duplicate writers must be tolerated.

Verification:

Static trace only. In a multi-worker smoke test, count rows inserted into both legacy tables over one interval and assert one sample per expected time bucket.

## Controls Confirmed

- EdgeEstimatorScheduler has process-local shutdown support and host-local leader election: `edge_estimator_scheduler.py:123-175` starts/stops a retained daemon thread, and `edge_estimator_scheduler.py:548-713` uses `fcntl.flock` so only one uvicorn worker runs the hourly estimator.
- Edge estimator routes surface leader/follower state instead of pretending every worker owns the scheduler: `edge_estimator_routes.py:47-92` returns 503 with leader PID for trigger misses, and `edge_estimator_routes.py:95-134` reports follower status.
- AIServiceListener has explicit multi-worker socket bind protection: `ai_service_listener.py:113-165` probes for an existing Unix-socket listener and passively no-ops on peer bind; `ai_service_listener.py:167-197` closes the server and unlinks the socket on shutdown.
- Rust uses engine-wide cancellation and ordered shutdown for core pipeline handles: `main.rs:244` creates the `CancellationToken`, `main.rs:1136-1155` runs signal handling then ordered shutdown, and `main_shutdown.rs:55-141` cancels, tears down Live/Demo slots, joins handles under a 10-second timeout, and removes the IPC socket.
- Rust interval helpers and watchdogs are cancellation-aware: `tasks/supervised_spawn.rs:113-143` implements a reusable cancel-aware interval loop, and `main_watchdog.rs:36-91` cancels the engine on stale ticks and exits on cancellation.
- The external watchdog has single-instance protection and restart backoff/circuit breaker: `engine_watchdog.py:661-676` uses `fcntl.flock`, `engine_watchdog.py:279-302` enforces maintenance/backoff checks, and `engine_watchdog.py:344-390` persists restart backoff state.
- Several Python in-process workers are locally idempotent and stoppable: `ttl_enforcer.py:466-505`, `h0_gate.py:861-903`, `executor_config_cache.py:179-220`, and `scout_worker.py:84-131`. These controls are process-local only and do not by themselves solve uvicorn multi-worker duplication.
- The Python MarketScanner path is currently stubbed: `program_code/local_model_tools/market_scanner.py:61-68` makes `start()`, `stop()`, and `scan()` no-ops/empty, so the ScoutWorker scan path is presently low impact.

## Files Reviewed

- `rust/openclaw_engine/src/main.rs`
- `rust/openclaw_engine/src/main_boot_tasks.rs`
- `rust/openclaw_engine/src/main_pipelines.rs`
- `rust/openclaw_engine/src/main_shutdown.rs`
- `rust/openclaw_engine/src/main_watchdog.rs`
- `rust/openclaw_engine/src/main_ws.rs`
- `rust/openclaw_engine/src/tasks.rs`
- `rust/openclaw_engine/src/tasks/supervised_spawn.rs`
- `rust/openclaw_engine/src/live_auth_watcher.rs`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ai_service.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ai_service_listener.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/evolution_auto_scheduler.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/experiment_ledger.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/experiment_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_wiring.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring_scanner.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/grafana_data_writer.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_config_cache.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ttl_enforcer.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/h0_gate.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/scout_worker.py`
- `program_code/local_model_tools/market_scanner.py`
- `helper_scripts/canary/engine_watchdog.py`
- `helper_scripts/restart_all.sh`
- `helper_scripts/stop_all.sh`
- `helper_scripts/fresh_start.sh`
- `helper_scripts/clean_restart.sh`
- `helper_scripts/cron_observer_cycle.sh`
- `helper_scripts/cron_daily_report.sh`
- `helper_scripts/db/counterfactual_daily_cron.sh`
- `helper_scripts/db/passive_wait_healthcheck_cron.sh`
- `helper_scripts/deploy/com.openclaw.engine-watchdog.plist`
- `helper_scripts/deploy/com.openclaw.engine.plist`
- `helper_scripts/deploy/com.openclaw.trading-api.plist`
