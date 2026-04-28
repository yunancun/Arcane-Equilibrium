# Live / Paper Mode Separation Audit

Created: 2026-04-28
Status: complete for this audit slice

## Scope

This slice reviewed live/paper startup boundaries, signed live authorization, pipeline slot teardown/respawn, paper enablement defaults, and operator scripts that can start services or flatten exchange state.

Primary files reviewed:

- `rust/openclaw_engine/src/main.rs`
- `rust/openclaw_engine/src/startup/mod.rs`
- `rust/openclaw_engine/src/live_authorization.rs`
- `rust/openclaw_engine/src/live_auth_watcher.rs`
- `rust/openclaw_engine/src/bybit_rest_client.rs`
- `rust/openclaw_engine/src/main_pipelines.rs`
- `rust/openclaw_engine/src/pipeline_slot.rs`
- `rust/openclaw_engine/src/tick_pipeline/mod.rs`
- `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth.py`
- `helper_scripts/restart_all.sh`
- `helper_scripts/clean_restart.sh`
- `helper_scripts/fresh_start.sh`
- `helper_scripts/clean_restart_flatten.py`
- `helper_scripts/start_paper_trading.sh`

## Confirmed Findings

### LP-001

Severity: P1
Status: open
Area: Live authorization / global mode separation
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py`
- `rust/openclaw_engine/src/live_auth_watcher.rs`
- `rust/openclaw_engine/src/startup/mod.rs`
- `rust/openclaw_engine/src/tick_pipeline/mod.rs`
- `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`

Summary:

`POST /api/v1/live/auth/renew` and `/auth/renew-review` can write a valid signed `authorization.json` and wake the Rust watcher without checking that the global mode is exactly `live_reserved`. The separate `/live/session/start` route does check global mode, but the Rust Live pipeline is driven by `authorization.json`, not by `/session/start`.

Evidence:

- `/live/session/start` checks Operator role and requires a global mode containing `live` before granting execution authority: `live_session_endpoints.py:139-164`.
- `/live/auth/renew` only requires Operator role, then creates live auth, writes signed `authorization.json`, triggers Rust auth recheck, and grants execution authority: `live_trust_routes.py:657-728`.
- `/live/auth/renew-review` has the same write-and-trigger path: `live_trust_routes.py:775-825`.
- Rust watcher respawns Live on `load_and_verify(self.env)` success with no global-mode check: `live_auth_watcher.rs:681-725`.
- Rust `build_exchange_pipeline()` gates Live on signed authorization only before constructing the exchange pipeline: `startup/mod.rs:495-521`.
- New `TickPipeline` instances default to `SystemMode::LiveReserved`: `tick_pipeline/mod.rs:38-44` and `tick_pipeline/pipeline_ctor.rs:111`.
- The tick dispatch gate blocks Live only when `system_mode` is `DemoReserved`, `ShadowOnly`, `ObserveOnly`, or `DesignOnly`; default `LiveReserved` allows dispatch: `tick_pipeline/on_tick/step_4_5_dispatch.rs:151-156`.

Impact:

An Operator-authenticated renewal can bring up the Live pipeline even when the GUI/control-plane global mode is still `design_only`, `observe_only`, `shadow_only`, or `demo_reserved`. On Mainnet, `OPENCLAW_ALLOW_MAINNET=1` and live slot credentials are still required; on LiveDemo, this bypasses the intended global-mode gate for the real Live code path.

Recommended fix:

- Require `global_mode_state == "live_reserved"` in both `/api/v1/live/auth/renew` and `/api/v1/live/auth/renew-review` before writing `authorization.json`.
- Replace substring checks such as `"live" in global_mode` with exact mode checks.
- Make Rust fail closed for newly spawned pipelines by defaulting `SystemMode` to `DesignOnly` or by loading a signed/persisted global mode fact before Live can dispatch.
- Consider including the approved system mode in the signed authorization payload so Rust can enforce it without trusting only Python request routing.

Verification:

Static trace only. No runtime service was started for this audit slice.

### LP-002

Severity: P2
Status: open
Area: Operator restart scripts
Files:

- `helper_scripts/clean_restart.sh`
- `helper_scripts/fresh_start.sh`
- `rust/openclaw_engine/Cargo.toml`

Summary:

`clean_restart.sh` and `fresh_start.sh` rebuild the Rust engine with `cargo build --release -p openclaw-engine`, but the Cargo package is named `openclaw_engine`. The hyphenated name is the binary name, not a valid package ID.

Evidence:

- `clean_restart.sh` uses `-p openclaw-engine` when binary is missing or stale: `clean_restart.sh:246-264`.
- `fresh_start.sh` uses `-p openclaw-engine` when binary is missing or stale: `fresh_start.sh:201-214`.
- `restart_all.sh` uses the correct package name `openclaw_engine`: `restart_all.sh:100-103`.
- Command result during audit: `cargo pkgid -p openclaw-engine --manifest-path rust/Cargo.toml` failed with `package ID specification 'openclaw-engine' did not match any packages`; `cargo pkgid -p openclaw_engine --manifest-path rust/Cargo.toml` succeeded.

Impact:

Clean/fresh restart paths fail during rebuild exactly when the operator most needs them: missing binary, stale binary, or source newer than release artifact. This can block recovery or cause operators to bypass freshness checks.

Recommended fix:

Change both scripts to `cargo build --release -p openclaw_engine --manifest-path rust/Cargo.toml` and add a lightweight script check that runs `cargo pkgid` for rebuild package names.

Verification:

Static command validation only; no release build was run.

### LP-003

Severity: P3
Status: open
Area: Paper startup automation
Files:

- `helper_scripts/start_paper_trading.sh`
- `helper_scripts/deploy/README.md`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py`
- `rust/openclaw_engine/src/main_pipelines.rs`

Summary:

`start_paper_trading.sh` is still documented as an auto-start path, but it targets stale response shapes and does not account for Rust Paper being disabled by default unless the engine process is launched with `OPENCLAW_ENABLE_PAPER=1`.

Evidence:

- Deploy docs still recommend `ExecStartPost=/bin/bash .../helper_scripts/start_paper_trading.sh`: `helper_scripts/deploy/README.md:184`.
- Rust disables Paper by default unless `OPENCLAW_ENABLE_PAPER=1`: `main_pipelines.rs:154-161`.
- The script reads `data.session_state`, but the paper status endpoint returns `data.session.session_state`: `start_paper_trading.sh:57-63` vs `paper_trading_routes.py:451-467`.
- The script reads `data.dispatcher_running`, but the market-feed status endpoint returns `data.running`: `start_paper_trading.sh:75-81` vs `paper_trading_routes.py:807-820`.

Impact:

The script can repeatedly issue no-op or failing startup calls and can report misleading startup status. In deployments where Paper is intentionally disabled, this creates operator confusion rather than enabling Paper.

Recommended fix:

Either retire the script from deployment docs, or update it to:

- require/verify `OPENCLAW_ENABLE_PAPER=1` in the engine environment,
- parse current response shapes,
- treat disabled Paper as an explicit success or skipped state,
- stop activating strategies through legacy assumptions when the Rust pipeline is not running.

Verification:

Static route/script comparison only.

## No-Finding Evidence

### Mainnet REST Construction Fails Closed

`BybitRestClient::new(Mainnet, ...)` requires `OPENCLAW_ALLOW_MAINNET=1`, ignores environment-variable API key fallback for Mainnet, and fails when live slot credentials are missing. Evidence: `bybit_rest_client.rs:520-557`.

The Python httpx client mirrors the same Mainnet opt-in and credential fallback rules. Evidence: `bybit_rest_client.py:163-200` and `bybit_rest_client.py:249-259`.

### Signed Authorization Has Strong Local Integrity Checks

Rust verifies schema version, HMAC, expiry, and endpoint label before accepting Live authorization. Evidence: `live_authorization.rs:281-352`.

Python writes `authorization.json` atomically with chmod 600 and signs the same canonical payload. Evidence: `live_trust_routes.py:107-209`.

### Authorization Revocation Tears Down Only Live

The watcher tears down only the Live slot when authorization becomes invalid, joins the prior Live OS thread, and clears Live command/event sender slots. Demo and Paper continue. Evidence: `live_auth_watcher.rs:857-949`.

`PipelineSlot` uses a slot-scoped child cancellation token so authorization revocation does not cancel the engine-wide token. Evidence: `pipeline_slot.rs:13-31` and `pipeline_slot.rs:59-91`.

### Manual Restart Sentinel Is Strict

`restart_all.sh` writes a strict `manual` sentinel by default before engine stop and supports `--keep-auth` as an explicit opt-out. Evidence: `restart_all.sh:132-178` and `restart_all.sh:180-197`.

Rust consumes the sentinel and treats only exact trimmed `manual` as manual restart; garbage or absent files map to `Auto`. Evidence: `restart_kind.rs:57-84`.

### Docker `change-me` API Token Is Not Accepted As Auth

The Dockerfile and Compose default `OPENCLAW_API_TOKEN=change-me`, but the auth resolver ignores `change-me` and falls back to a token file or auto-generates a new token. Evidence: `Dockerfile:12-17`, `docker-compose.yml:12-14`, and `auth.py:106-129`.

## Follow-Up Targets

- Order execution and reconciliation should inspect whether Live pipeline startup can place new exchange orders before an explicit system-mode broadcast reaches the respawned pipeline.
- API authorization review should cover write endpoints that use `current_actor` without an explicit role/scope check, especially risk config and strategy activation routes.
- Operator script review should continue with `stop_all.sh`, `engine_watchdog.py`, and DB reset scripts.
