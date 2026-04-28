# Operator Scripts Audit

Created: 2026-04-28
Status: complete

## Scope

This segment reviewed non-test operator, maintenance, deployment, and cron scripts:

- Restart, stop, clean restart, fresh start, and exchange flatten scripts.
- Destructive DB reset, migration cleanup, and migration apply wrappers.
- Bootstrap scripts for macOS/Linux DB and runtime setup.
- Cron wrappers for observer, daily reports, counterfactual replay, and passive health checks.
- launchd plist templates and deployment runbook snippets.
- Operator IPC wrappers for risk-config flips and related emergency actions.

Tests were excluded. No live exchange, database, launchd service, cron entry, or secret file was executed.

## Reviewed Runtime Paths

- `helper_scripts/restart_all.sh`
- `helper_scripts/stop_all.sh`
- `helper_scripts/clean_restart.sh`
- `helper_scripts/fresh_start.sh`
- `helper_scripts/clean_restart_flatten.py`
- `helper_scripts/start_paper_trading.sh`
- `helper_scripts/mac_bootstrap.sh`
- `helper_scripts/mac_bootstrap_db.sh`
- `helper_scripts/linux_bootstrap_db.sh`
- `helper_scripts/cron_daily_report.sh`
- `helper_scripts/cron_observer_cycle.sh`
- `helper_scripts/db/fresh_start_reset.py`
- `helper_scripts/db/cleanup_v026_partial_state.sh`
- `helper_scripts/db/deploy_V017.sh`
- `helper_scripts/db/deploy_V018.sh`
- `helper_scripts/db/counterfactual_daily_cron.sh`
- `helper_scripts/db/passive_wait_healthcheck_cron.sh`
- `helper_scripts/maintenance_scripts/prune_dated_files.sh`
- `helper_scripts/operator/edge_p2_flip.sh`
- `helper_scripts/deploy/README.md`
- `helper_scripts/deploy/com.openclaw.engine.plist`
- `helper_scripts/deploy/com.openclaw.engine-watchdog.plist`
- `helper_scripts/deploy/com.openclaw.trading-api.plist`
- `helper_scripts/deploy/com.openclaw.gateway.plist`

## Flow Summary

The operator surface is split between service lifecycle scripts, one-off repair/reset scripts, cron wrappers, and deployment templates. `restart_all.sh` is the most complete lifecycle path: it writes the manual-restart sentinel, tries graceful engine shutdown, rotates the engine log, clears the maintenance flag, rebuilds when requested, and starts engine/API with DB and IPC secrets taken from the secrets root. `stop_all.sh` intentionally creates the maintenance flag before stopping the engine.

`clean_restart.sh` and `fresh_start.sh` are heavier maintenance paths. Both stop local processes, optionally flatten exchange positions through the Python Bybit REST client, archive runtime files, and restart engine/API. `fresh_start.sh` additionally executes `fresh_start_reset.py`, which truncates many trading, agent, learning, observability, and risk tables after archiving LinUCB state.

The deployment templates are mostly manual runbooks. The launchd path depends on an operator replacing placeholders and injecting DB/IPC/provider secrets through `launchctl setenv`; there is no installer that validates the final environment before loading services.

Several risks from this segment were already recorded in previous audit chapters and are not duplicated here: stale cargo package ID in clean/fresh restart (`LP-002`), operator scripts carrying secrets in argv/env (`SC-005`), missing maintenance flag in `clean_restart.sh` (`SW-001`), and cron overlap locks (`SW-006`).

## Findings

### OS-001

Severity: P1
Status: open
Area: Live exchange flattening
Files:

- `helper_scripts/clean_restart.sh`
- `helper_scripts/fresh_start.sh`
- `helper_scripts/clean_restart_flatten.py`

Summary:

The clean/fresh restart live-flatten path can cancel mainnet orders and place reduce-only mainnet market orders through the Python Bybit REST client without checking the signed Live authorization/global-mode control plane.

Evidence:

- `clean_restart.sh:164-171` runs `clean_restart_flatten.py --env mainnet` when `--include-live` and `OPENCLAW_ALLOW_MAINNET=1` are present.
- `fresh_start.sh:138-145` exposes the same mainnet flatten path.
- `clean_restart.sh:155` and `fresh_start.sh:133` forward `--yes` to the flatten helper, bypassing the helper confirmation.
- `clean_restart_flatten.py:47` constructs `BybitClient(environment=args.env)` directly.
- `clean_restart_flatten.py:102-141` cancels open orders and submits reduce-only market orders.
- `clean_restart_flatten.py:167-170` repeats reduce-only market sweeps for residual positions.

Impact:

An operator command or automation with live credentials and `OPENCLAW_ALLOW_MAINNET=1` can mutate mainnet exchange state outside the Rust live engine, signed `authorization.json`, `live_reserved` global-mode checks, and normal order audit path. The orders are reduce-only, but they still close real positions and cancel live orders.

Trigger:

Run `helper_scripts/clean_restart.sh --include-live --yes` or `helper_scripts/fresh_start.sh --include-live --yes` with live credentials configured and `OPENCLAW_ALLOW_MAINNET=1`.

Recommended fix:

Route live flattening through the same signed live-control boundary used by the engine, require a current `live_reserved` authorization, and require a second typed mainnet confirmation that cannot be skipped by the generic `--yes`. Make dry-run/position plan output the default for mainnet and persist a per-symbol flatten audit row before exchange writes.

Verification:

Static trace only.

### OS-002

Severity: P1
Status: open
Area: Destructive DB reset scripts
Files:

- `helper_scripts/fresh_start.sh`
- `helper_scripts/db/fresh_start_reset.py`
- `helper_scripts/clean_restart.sh`
- `helper_scripts/db/cleanup_v026_partial_state.sh`

Summary:

Destructive DB reset paths can run against the configured local database without a production/environment guard, and `fresh_start.sh --yes` auto-generates the confirmation token that the reset helper was meant to require.

Evidence:

- `fresh_start.sh:55` generates `CONFIRM_CODE="FRESH_START_$(date +%Y_%m_%d)"`.
- `fresh_start.sh:111` allows the top-level destructive prompt to be skipped through `--yes`.
- `fresh_start.sh:187-192` sources the secrets env and calls `fresh_start_reset.py --execute --confirm "$CONFIRM_CODE"`.
- `fresh_start_reset.py:493-506` requires the same date-derived token, so the wrapper can satisfy it automatically.
- `fresh_start_reset.py:380-395` executes `TRUNCATE ... RESTART IDENTITY CASCADE` across the wipe table list.
- `clean_restart.sh:223-236` creates backup tables then truncates `trading.fills`, `trading.intents`, `trading.orders`, and `trading.risk_verdicts` under `--mark-damaged`.
- `cleanup_v026_partial_state.sh:21-26` defaults to `postgresql:///openclaw` and drops `learning.cost_edge_advisor_log` without dry-run or confirmation.

Impact:

A wrong shell environment, stale secrets root, pasted command, or automation run can wipe durable trading/learning/audit history in the wrong database. The scripts are useful for development and incident recovery, but the current guard is mostly operator intent rather than an enforceable target/environment contract.

Trigger:

Run `helper_scripts/fresh_start.sh --yes` or `helper_scripts/clean_restart.sh --yes --mark-damaged` on a host whose secrets point at an unintended database.

Recommended fix:

Require explicit target environment and database identity checks before destructive writes. For example, require `OPENCLAW_ALLOW_DB_WIPE=<db_fingerprint>`, show server/database/schema row counts, require a typed token that includes the actual DB name/host/date, and prevent wrappers from generating the helper confirmation token. Keep dry-run as the default for standalone cleanup scripts.

Verification:

Static trace only.

### OS-003

Severity: P2
Status: open
Area: Process control
Files:

- `helper_scripts/restart_all.sh`
- `helper_scripts/stop_all.sh`
- `helper_scripts/clean_restart.sh`
- `helper_scripts/fresh_start.sh`

Summary:

Lifecycle scripts identify processes by broad command-line substrings and kill any process listening on port 8000, not just processes owned by this repo instance.

Evidence:

- `stop_all.sh:49-64` finds and kills any process matching `openclaw-engine`.
- `stop_all.sh:70-81` terminates or kills every PID returned by `lsof -ti :8000`.
- `restart_all.sh:197-213` uses the same broad `pgrep/pkill -f "openclaw-engine"` pattern.
- `restart_all.sh:254` kills all listeners on port 8000 before starting the API.
- `clean_restart.sh:130-138` uses broad `pkill -f "openclaw-engine"` and `lsof -ti :8000 | xargs kill -9`.
- `fresh_start.sh:120-123` uses the same broad kill pattern.

Impact:

On a development host, a second checkout, a different Uvicorn app, or a service-manager-controlled instance on port 8000 can be killed by these scripts. In production, this can create duplicate manager/manual lifecycle state, kill the wrong service, or interrupt unrelated local tooling.

Trigger:

Run any restart/stop/clean/fresh script while another process matching `openclaw-engine` exists or any non-OpenClaw process is bound to port 8000.

Recommended fix:

Use PID files, service-manager labels, socket activation metadata, or process executable/cwd validation before killing. Prefer `systemctl --user`/`launchctl` for managed services, and have manual scripts refuse to operate when the discovered process does not match the expected binary path and working directory.

Verification:

Static trace only.

### OS-004

Severity: P2
Status: open
Area: Maintenance flag recovery
Files:

- `helper_scripts/fresh_start.sh`

Summary:

`fresh_start.sh` creates the watchdog maintenance flag but does not protect cleanup with an `EXIT`/`ERR`/signal trap, so unexpected failures can leave watchdog recovery disabled.

Evidence:

- `fresh_start.sh:67` defines `MAINT_FLAG="$DATA_DIR/engine_maintenance.flag"`.
- `fresh_start.sh:117` creates the flag before stopping the engine.
- `fresh_start.sh:132`, `fresh_start.sh:136`, `fresh_start.sh:145`, and `fresh_start.sh:192` remove it only for a few explicit error branches.
- `fresh_start.sh:203-214` can fail during cargo build without a local cleanup branch.
- `fresh_start.sh:223` removes the flag only if execution reaches restart step 7.
- `rg -n "trap" helper_scripts/fresh_start.sh` found no cleanup trap.

Impact:

If the script is interrupted or fails outside the explicit handled branches, `engine_maintenance.flag` can remain in place while the engine/API are down. The watchdog will then treat the outage as operator maintenance and avoid restart.

Trigger:

Interrupt `fresh_start.sh` after line 117, or let it fail during binary freshness/build/restart verification.

Recommended fix:

Install a trap immediately after creating the maintenance flag. The trap should clear or convert the flag to a TTL-scoped maintenance lease unless the script reaches a deliberately stopped/maintenance terminal state. Also record the reason and timestamp in the flag body so the watchdog can alert on stale maintenance.

Verification:

Static trace only.

### OS-005

Severity: P2
Status: open
Area: macOS launchd deployment
Files:

- `helper_scripts/deploy/README.md`
- `helper_scripts/deploy/com.openclaw.engine.plist`
- `helper_scripts/deploy/com.openclaw.trading-api.plist`
- `helper_scripts/deploy/com.openclaw.gateway.plist`

Summary:

The macOS deployment runbook loads launchd services before injecting required secrets/env, and the templates do not include an installer/preflight that rejects missing values or placeholder provider keys.

Evidence:

- `deploy/README.md:238-244` loads engine, watchdog, trading API, and gateway plists.
- `deploy/README.md:247-253` documents `launchctl setenv OPENCLAW_IPC_SECRET` and `OPENCLAW_DATABASE_URL` only after the load commands, with a note that unload/load is required afterward.
- `com.openclaw.engine.plist:64-67` says sensitive `IPC_SECRET`/`DATABASE_URL` must be injected via `launchctl setenv`, but the plist itself cannot verify that.
- `com.openclaw.trading-api.plist:80-104` includes runtime variables and `BYBIT_API_HOST`, but not the DB URL or IPC secret expected by many API routes/scripts.
- `com.openclaw.gateway.plist:76-82` contains placeholder provider key values.

Impact:

The documented first load can start services with missing DB/IPC/provider environment, leading to failed startup, fallback behavior, stale auth/IPC assumptions, or a gateway running with placeholder credentials. Operators then have to unload/reload manually to correct the environment, which is easy to miss during migration.

Trigger:

Follow the macOS deployment README in order on a fresh login session.

Recommended fix:

Replace the manual runbook with an installer script that sets env first, verifies `launchctl getenv` for required keys, rejects placeholder values, validates `__BASE__` replacement, and only then loads services. Add a `doctor` mode that compares launchd environment with the secrets root and refuses live/demo service start on mismatch.

Verification:

Static trace only.

### OS-006

Severity: P2
Status: open
Area: Database bootstrap privilege and SQL construction
Files:

- `helper_scripts/mac_bootstrap_db.sh`

Summary:

The macOS DB bootstrap creates the application role as PostgreSQL `SUPERUSER` and interpolates the password directly into an SQL string without SQL literal escaping.

Evidence:

- `mac_bootstrap_db.sh:44-53` builds a temporary SQL file and creates `trading_admin WITH LOGIN SUPERUSER`, then writes `ALTER ROLE trading_admin WITH PASSWORD '%s'`.
- `mac_bootstrap_db.sh:75` verifies login as `trading_admin`.
- `mac_bootstrap_db.sh:90-95` runs initialization SQL as `trading_admin`.
- `mac_bootstrap_db.sh:107-110` applies every migration as `trading_admin`.

Impact:

Any runtime/API compromise of `trading_admin` becomes a cluster-level database compromise on this deployment path. A password containing a single quote can also break the bootstrap SQL or be interpreted as additional SQL, depending on the env-file content.

Trigger:

Run `mac_bootstrap_db.sh` with a fresh local PostgreSQL container and the standard secrets env file.

Recommended fix:

Use separate owner/migration/runtime roles. Keep superuser only for the initial extension/bootstrap actor, then run migrations with a schema owner and runtime services with least-privilege DML grants. Pass the password through `psql` variables or a safe SQL-literal quoting mechanism instead of interpolating it into SQL text.

Verification:

Static trace only.

### OS-007

Severity: P3
Status: open
Area: Daily report cron robustness
Files:

- `helper_scripts/cron_daily_report.sh`

Summary:

The daily Telegram report builds JSON by shell string interpolation and places the bot token in the curl URL argument.

Evidence:

- `cron_daily_report.sh:101-117` builds a multi-line `MSG` from API and shell values.
- `cron_daily_report.sh:120-125` builds `TELEGRAM_API="https://api.telegram.org/bot${BOT_TOKEN}/sendMessage"` and posts a hand-built JSON string with `-d`.
- The message text is not JSON-escaped before insertion.

Impact:

Quotes, backslashes, or literal newlines in the message can produce invalid JSON or malformed Markdown. The bot token is also visible in the curl process arguments while the request is in flight, which reinforces `SC-005` for this specific cron path.

Trigger:

Run the cron script with report content containing JSON-significant characters or inspect process arguments during a slow Telegram request.

Recommended fix:

Build the payload with `jq -n` or a small Python helper so text is JSON-escaped. Move the HTTP call into Python or a curl config/stdin path that avoids putting the tokenized URL in argv, and keep report push failures visible in cron/healthcheck status.

Verification:

Static trace only.

## Residual Notes

- `restart_all.sh` is materially safer than the older clean/fresh lifecycle paths because it writes the manual restart sentinel, rotates logs, and uses the correct Cargo package ID. The broad kill matching still applies.
- `linux_bootstrap_db.sh` has a useful dry-run default, but it intentionally relies on idempotent SQL files and tells operators to run `audit_migrations.py` for silent no-op detection. That larger schema drift issue is covered by the database migration audit.
- `operator/edge_p2_flip.sh` has better guard shape than most shell wrappers: it runs a dry-run by default, requires confirmation unless explicitly skipped, verifies the IPC mutation, and logs the workflow. Its `--skip-confirm` and `--skip-dry-run` flags should remain restricted to controlled automation.
