# Secrets and Credentials Audit

Created: 2026-04-28
Status: complete for this audit slice
Scope: Control API authentication token and GUI login credentials, Bybit API key slots, live authorization signing, IPC HMAC, Docker/launchd credential propagation, monitoring credentials, and operator scripts that pass secrets to local commands.

## Scope Note

This audit did not open real `.env`, `secret_files`, `environment_files`, or generated `.secrets` values. It reviewed code paths, templates, documentation, and committed configuration. A redacted high-confidence secret pattern scan over in-scope non-test files found one committed probable secret-bearing file: the Grafana FastAPI datasource provisioning file.

## Flow Summary

Control API authentication is backed by a single bearer token resolved from `OPENCLAW_API_TOKEN`, `OPENCLAW_API_TOKEN_FILE`, or `control_api_v1/.secrets/api_token`; if none is valid, the API auto-generates and stores a token. The authenticated actor is then built from configured `OPENCLAW_AUTH_*` identity, roles, and scopes.

GUI login uses `gui_auth.env` for username/password, then sets an HttpOnly `oc_auth_token` cookie containing the same Control API bearer token. API clients may still pass the same token through `Authorization: Bearer ...`.

Bybit credentials are stored in slot files under `OPENCLAW_SECRETS_DIR/{demo,live}/api_key|api_secret` or the home-directory fallback. Mainnet credential loading intentionally ignores `BYBIT_API_KEY` and `BYBIT_API_SECRET` env fallback and requires `OPENCLAW_ALLOW_MAINNET=1`. Live pipeline authorization is separately gated by a HMAC-signed `authorization.json` under the live slot and `OPENCLAW_IPC_SECRET`.

## Confirmed Findings

### SC-001

Severity: P1
Status: open
Area: Control API bearer token lifecycle
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main_legacy.py`
- `docker_projects/trading_services/openclaw_bybit_control_api_v1/docker-compose.yml`
- `docker_projects/trading_services/openclaw_bybit_control_api_v1/DEPLOY_README.md`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/API_TOKEN_RESET_GUIDE.md`

Summary:

When the Control API token is missing or set to `change-me`, the server auto-generates a new token and prints the full value to stderr. That token authenticates as the default actor, whose default roles include `operator`.

Evidence:

- `_resolve_api_token()` ignores `OPENCLAW_API_TOKEN=change-me`, auto-generates a token, writes it to `.secrets/api_token`, and prints `Token: {new_token}` to stderr at `auth.py:107-145`.
- Default `OPENCLAW_AUTH_ROLES` includes `operator` and other privileged roles at `auth.py:159-165`.
- `current_actor()` compares the bearer/cookie token and then returns `build_authenticated_actor()` at `main_legacy.py:389-418`; the actor roles are copied from settings at `main_legacy.py:219-225`.
- The Docker compose file defaults `OPENCLAW_API_TOKEN` to `change-me` at `docker-compose.yml:12-14`, and the deploy README tells operators to export `OPENCLAW_API_TOKEN='change-me'` at `DEPLOY_README.md:24` and `:66`.
- The token reset guide documents stderr disclosure as expected behavior at `API_TOKEN_RESET_GUIDE.md:68-76`.

Impact:

First-run or misconfigured deployments can leak an operator-capable bearer token through container logs, launchd logs, terminal scrollback, or log aggregation. The `change-me` deployment guidance also increases the chance this path is hit in production-like setups.

Reproduction or trigger:

Start the Control API without a valid token file/env var, or with `OPENCLAW_API_TOKEN=change-me`.

Recommended fix:

Do not print the generated token value. Print only the file path and chmod instructions. For production/docker, fail closed unless a non-placeholder token or explicit token file is provided. Consider defaulting roles to `viewer` unless operator roles are explicitly configured.

Verification:

Static trace only.

### SC-002

Severity: P1
Status: open
Area: GUI login credential validation
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth_routes_common.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth_legacy_routes.py`

Summary:

`gui_auth.env` validation rejects a missing or placeholder username but does not reject a missing, empty, or placeholder password.

Evidence:

- `load_expected_credentials()` reads `GUI_USERNAME` and `GUI_PASSWORD`, checks only `expected_user`, and returns `expected_pass` even when it is empty at `auth_routes_common.py:127-148`.
- `verify_login_credentials()` then constant-time compares the submitted password to that value at `auth_routes_common.py:201-210`.
- The login route calls these helpers and sets the auth cookie on success at `auth_legacy_routes.py:83-100`.

Impact:

If `gui_auth.env` contains a valid username but lacks `GUI_PASSWORD` or has it blank, a login with an empty password succeeds and receives the full Control API bearer cookie.

Reproduction or trigger:

Create `gui_auth.env` with `GUI_USERNAME=<non-placeholder>` and no `GUI_PASSWORD`, or with `GUI_PASSWORD=`. Submit the username with an empty password.

Recommended fix:

Require a non-empty password and reject known placeholders such as `YOUR_PASSWORD`, `change-me`, or short values. Add startup validation and login tests for missing/blank/placeholder password.

Verification:

Static trace only.

### SC-003

Severity: P1
Status: open
Area: Committed monitoring credential
Files:

- `docker_projects/monitoring_services/provisioning/datasources/fastapi.yml`

Summary:

The Grafana FastAPI datasource provisioning file contains a committed literal `Authorization: Bearer ...` value.

Evidence:

`fastapi.yml:7-10` provisions the datasource header name and a hard-coded bearer value in `secureJsonData`.

Impact:

If this token is valid for the Control API, the repository contains an operator-capable API credential. If it is stale, monitoring silently fails until someone discovers the mismatch. Either way, the repo is carrying a secret-shaped value where an injected secret reference should be used.

Reproduction or trigger:

Start the monitoring compose stack with this provisioning file.

Recommended fix:

Remove the literal token from the repository, rotate it if it was ever valid, and provision Grafana from an environment variable or mounted secret file. Add a secret scanner rule to fail CI on bearer literals in committed config.

Verification:

Static trace only. A redacted high-confidence secret pattern scan identified this as the only probable committed runtime secret in the reviewed non-test scope.

### SC-004

Severity: P2
Status: open
Area: Monitoring access control
Files:

- `docker_projects/monitoring_services/docker-compose.yml`

Summary:

The Grafana compose file hard-codes the admin password and enables anonymous Viewer access while publishing port `3000`.

Evidence:

`docker-compose.yml:6-14` maps `3000:3000`, sets a fixed `GF_SECURITY_ADMIN_PASSWORD`, enables anonymous auth, and grants anonymous users the Viewer role.

Impact:

On any host where this compose stack is reachable beyond localhost or a trusted network, dashboards can be viewed anonymously and admin access is protected by a repository-known password.

Reproduction or trigger:

Run the monitoring compose stack as-is on a network-accessible host.

Recommended fix:

Move the Grafana admin password to an injected secret, disable anonymous access by default, and bind the port to localhost unless explicitly overridden.

Verification:

Static trace only.

### SC-005

Severity: P2
Status: open
Area: Secret propagation through process argv/env
Files:

- `helper_scripts/db/deploy_V017.sh`
- `helper_scripts/db/deploy_V018.sh`
- `helper_scripts/restart_all.sh`
- `helper_scripts/clean_restart.sh`
- `helper_scripts/fresh_start.sh`
- `helper_scripts/cron_daily_report.sh`
- `helper_scripts/start_paper_trading.sh`
- `helper_scripts/deploy/README.md`

Summary:

Several operator scripts pass database passwords, IPC secrets, API bearer tokens, or Telegram bot tokens through command arguments or long-lived process environments.

Evidence:

- `deploy_V017.sh` and `deploy_V018.sh` build a `postgresql://redacted@...` DSN at line `35` and pass it to `psql "$DSN"` at `deploy_V017.sh:57`, `:75`, and `:79`.
- `restart_all.sh` launches the engine/API with `OPENCLAW_DATABASE_URL=postgresql://redacted@...` and `OPENCLAW_IPC_SECRET=...` in the process environment at `restart_all.sh:243-248` and `:275-279`.
- `clean_restart.sh` and `fresh_start.sh` do the same at `clean_restart.sh:275-290` and `fresh_start.sh:226-239`.
- `cron_daily_report.sh` builds a Telegram Bot API URL containing the bot token and passes it to `curl` at `cron_daily_report.sh:120-124`.
- `start_paper_trading.sh` constructs `Authorization: Bearer $OPENCLAW_API_TOKEN` and passes it to `curl -H` at `start_paper_trading.sh:31-39`.
- `deploy/README.md:247-252` recommends `launchctl setenv` for IPC secret and DB URL, which exposes those values broadly to the user launchd environment.

Impact:

Local same-user processes, shell history, crash diagnostics, process listings, or launchd environment inspection can expose high-value secrets. This is a local-host threat, but the leaked values include DB credentials, IPC HMAC secret, Control API token, and Telegram bot token.

Reproduction or trigger:

Run the scripts and inspect active process command lines/environments from the same user account while `psql`, `curl`, engine, API, or launchd agents are active.

Recommended fix:

Prefer `.pgpass`, libpq service files, fd-passed secret files, or mounted secret files over DSN arguments. Avoid putting bot tokens in URLs where possible. For long-running services, pass paths to `0600` secret files and load them inside the process, rather than setting full secrets in launchd/global env.

Verification:

Static trace only.

### SC-006

Severity: P2
Status: open
Area: Launchd AI provider secret handling
Files:

- `helper_scripts/deploy/com.openclaw.gateway.plist`

Summary:

The gateway launchd template includes `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` inside the plist `EnvironmentVariables` block and instructs operators to fill them manually.

Evidence:

`com.openclaw.gateway.plist:62-81` contains placeholder entries for both API keys inside the checked-in plist template.

Impact:

This invites operators to write provider keys directly into a plist file that lives in the repository tree before copy/install. That increases the chance of accidental commits, file backups, and long-lived plaintext provider keys in launchd-managed configuration.

Reproduction or trigger:

Follow the template comment by editing the plist in-place with real provider keys.

Recommended fix:

Mirror the engine plist pattern: do not include secret key fields in the plist template. Use `launchctl setenv` only as a short-term local option, and prefer secret files or Keychain-backed injection for provider API keys.

Verification:

Static trace only.

### SC-007

Severity: P2
Status: open
Area: Auth cookie transport security
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth_routes_common.py`

Summary:

The auth cookie `Secure` attribute is based solely on `request.url.scheme == "https"`.

Evidence:

`set_auth_cookie()` sets `httponly=True`, `samesite="strict"`, and `secure=request.url.scheme == "https"` at `auth_routes_common.py:151-168`.

Impact:

Behind a TLS-terminating proxy that forwards to Uvicorn over HTTP without trusted proxy scheme handling, the app can issue an auth cookie without `Secure`. If the API is also reachable over HTTP, the operator bearer cookie can be sent in cleartext.

Reproduction or trigger:

Deploy behind a reverse proxy that terminates TLS but presents `request.url.scheme` as `http`, then log in and inspect the `Set-Cookie` attributes.

Recommended fix:

Add a production setting such as `OPENCLAW_COOKIE_SECURE=1` that forces `Secure`, or configure trusted proxy headers and fail closed for non-localhost HTTP in production.

Verification:

Static trace only.

## Controls Confirmed

- `.env`, `environment_files`, `secret_files`, and `control_api_v1/.secrets/` are ignored by Git configuration.
- Settings API key GET returns masked hints, not plaintext keys.
- Settings API key POST is operator-gated, validates keys before writing, whitelists slots, and writes files with `0600`.
- Python and Rust Bybit mainnet clients ignore `BYBIT_API_KEY` / `BYBIT_API_SECRET` env fallback and require slot files plus `OPENCLAW_ALLOW_MAINNET=1`.
- Live authorization is HMAC-signed, checks TTL and environment allow-list, and uses constant-time signature comparison.
- IPC HMAC requires a 30-second timestamp window when `OPENCLAW_IPC_SECRET` is set; Rust fails closed for live pipeline startup if the IPC secret is absent.

## Files Reviewed

- `.gitignore`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/.gitignore`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/.env.example`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/API_TOKEN_RESET_GUIDE.md`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth_routes_common.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth_legacy_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main_legacy.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/settings_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ipc_client.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/db_pool.py`
- `rust/openclaw_engine/src/bybit_rest_client.rs`
- `rust/openclaw_engine/src/live_authorization.rs`
- `rust/openclaw_engine/src/ipc_server/connection.rs`
- `rust/openclaw_engine/src/main.rs`
- `docker_projects/monitoring_services/docker-compose.yml`
- `docker_projects/monitoring_services/provisioning/datasources/fastapi.yml`
- `docker_projects/trading_services/openclaw_bybit_control_api_v1/docker-compose.yml`
- `docker_projects/trading_services/openclaw_bybit_control_api_v1/DEPLOY_README.md`
- `helper_scripts/db/deploy_V017.sh`
- `helper_scripts/db/deploy_V018.sh`
- `helper_scripts/restart_all.sh`
- `helper_scripts/clean_restart.sh`
- `helper_scripts/fresh_start.sh`
- `helper_scripts/cron_daily_report.sh`
- `helper_scripts/start_paper_trading.sh`
- `helper_scripts/deploy/README.md`
- `helper_scripts/deploy/com.openclaw.engine.plist`
- `helper_scripts/deploy/com.openclaw.trading-api.plist`
- `helper_scripts/deploy/com.openclaw.gateway.plist`
- `settings/secret_files/README.md`
- `settings/secret_files/bybit/README.md`
