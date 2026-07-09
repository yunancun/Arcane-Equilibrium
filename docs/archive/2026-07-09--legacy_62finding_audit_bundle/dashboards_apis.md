# Dashboards and APIs Audit

Created: 2026-04-28
Status: complete

## Scope

This segment reviewed non-test dashboard and HTTP API surfaces:

- FastAPI app composition, router registration, auth dependencies, role/scope checks, and CORS/security headers.
- State-changing endpoints for AI budget, paper/session controls, strategy/risk config, scheduled restart, model registry, live/trust, governance, experiments, backtests, and evolution.
- Dashboard HTML/static auth assumptions and GUI fetch behavior.
- Dashboard/data routes that read database state, runtime snapshots, IPC state, and local health state.
- API-side process, proxy, file, and shell command surfaces.

Tests were excluded. No live API server, database, exchange account, or secret file was exercised.

## Reviewed Runtime Paths

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main_legacy.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth_legacy_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth_routes_common.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/gui_legacy_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/system_legacy_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_legacy_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ai_budget_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ml_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_write_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/settings_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_account_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_extended_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_promotion_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_promote_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/engine_capabilities_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/shadow_fills_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/experiment_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/evolution_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/backtest_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/common.js`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/console.html`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/trading.html`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/index.html`
- `helper_scripts/restart_all.sh`

## Flow Summary

The primary HTTP service is `app.main:app`, which patches the core state-store helpers from `main_legacy.py` and then includes domain routers. Most legacy API reads and writes use `current_actor`, which accepts either the HttpOnly GUI cookie or a bearer token and maps it to one configured static actor. The newer governance, model-promotion, backtest, and evolution routes often add explicit operator-role checks; legacy control operations additionally use `require_scope_and_identity` inside operation helpers.

The API has several intentionally unauthenticated endpoints: login/logout/check, minimal liveness, startup status, and some dashboard HTML. That is acceptable only when the response is minimal and cannot mutate state. The reviewed code also contains unauthenticated or under-authorized routes that mutate engine state, expose database/model internals, or rely on blocked client JavaScript for auth enforcement.

The GUI is a static HTML/JS dashboard backed by authenticated JSON routes. Static assets under `/static` are protected by middleware except a small exemption list, but top-level HTML routes are not server-side guarded.

## Findings

### DAPI-001

Severity: P1
Status: open
Area: API authorization / AI budget mutation
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ai_budget_routes.py`

Summary:

`POST /api/v1/ai_budget/config` has no authentication or operator dependency, yet it updates AI budget config through Rust IPC.

Evidence:

- `main.py:176-178` includes `ai_budget_router` in the public FastAPI app.
- `ai_budget_routes.py:40` creates the router at `/api/v1/ai_budget`.
- `ai_budget_routes.py:171-172` defines `update_ai_budget_config_route(payload)` without `Depends(current_actor)`, `_get_auth_actor`, or an operator guard.
- `ai_budget_routes.py:199-204` sends `update_ai_budget_config` to the engine with caller-supplied `scope`, `monthly_usd`, and `updated_by`.

Impact:

An unauthenticated caller who can reach the API can set AI budgets to zero, very high values, or misleading `updated_by` values. This can disable AI-assisted workflows through budget exhaustion semantics or remove budget pressure intended to limit model/API spend.

Trigger:

Send `POST /api/v1/ai_budget/config` with any JSON body satisfying `BudgetConfigUpdate`, without cookie or bearer token.

Recommended fix:

Add `actor = Depends(base.current_actor)` or the shared `_get_auth_actor` dependency, require operator role, and consider a dedicated `ai_budget:write` scope. Ignore or overwrite client-supplied `updated_by` with the authenticated actor id.

Verification:

Static trace only.

### DAPI-002

Severity: P2
Status: open
Area: Unauthenticated model registry observability
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ml_routes.py`

Summary:

`GET /api/v1/ml/model_registry` and `GET /api/v1/ml/model_info` are unauthenticated direct PostgreSQL-backed routes that expose model artifact paths, promotion state, training sample sizes, schema hashes, and DB error details.

Evidence:

- `main.py:204-211` includes `ml_router`.
- `ml_routes.py:183-192` defines `list_registry` with no auth dependency and comments that no authentication is required.
- `ml_routes.py:203-208` includes `artifact_path`, `feature_schema_hash`, `training_sample_size`, and `acceptance_report` in the returned columns.
- `ml_routes.py:256-260` defines `model_info` with no auth dependency.
- `ml_routes.py:281-291` returns artifact path, canary status, verdict, train date, and artifact hash for the selected slot.
- `ml_routes.py:152-166` and `ml_routes.py:243-245` surface connection/query failure detail to the HTTP response.

Impact:

Unauthenticated callers can enumerate internal model inventory and filesystem artifact paths, infer active strategies/engines, and probe database availability. This is inconsistent with the rest of the dashboard data API, which generally requires `current_actor`.

Trigger:

Call either model registry GET endpoint without authentication while the API is reachable.

Recommended fix:

Require authenticated read access for model registry routes, preferably a `learning:read` or `model_registry:read` scope. Keep public liveness separate from operational/model metadata, and return generic 503/500 bodies while logging DB details server-side.

Verification:

Static trace only.

### DAPI-003

Severity: P2
Status: open
Area: Authenticated reverse proxy token leakage
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`

Summary:

The `/openclaw/{path}` reverse proxy strips the `Authorization` header but forwards the caller's `Cookie` header, including the HttpOnly `oc_auth_token`, to the downstream OpenClaw gateway host.

Evidence:

- `main.py:565-567` exposes `/openclaw/{path}` for authenticated callers.
- `main.py:563` allows the downstream host to be configured by `OPENCLAW_GATEWAY_HOST`.
- `main.py:572-578` copies request headers except `host`, `transfer-encoding`, and `authorization`; `cookie` is not stripped.
- The auth cookie is accepted as the bearer credential by `main_legacy.py:401-418`.

Impact:

The API bearer token can be forwarded to a downstream service that does not need it. If the gateway logs headers, is compromised, or `OPENCLAW_GATEWAY_HOST` is misconfigured, the token may leak despite being HttpOnly in the browser.

Trigger:

Authenticate to the GUI, then request any `/openclaw/*` path. The browser sends `Cookie: oc_auth_token=...`, and the proxy forwards it to the gateway.

Recommended fix:

Strip `cookie` and other credential-bearing headers when proxying to the gateway. Forward only a minimal allowlist of safe headers, and add a regression that asserts neither `Authorization` nor `Cookie` reaches the downstream request.

Verification:

Static trace only.

### DAPI-004

Severity: P2
Status: open
Area: GUI HTML authentication boundary
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/gui_legacy_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main_legacy.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/common.js`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/console.html`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/trading.html`

Summary:

Top-level GUI HTML routes are served without server-side auth and rely on browser-side JavaScript redirects. For `/console` and `/trading`, the redirect script is in `/static/common.js`, but unauthenticated access to that JS file is blocked by the static auth middleware, so the redirect may not execute.

Evidence:

- `gui_legacy_routes.py:13-26` explicitly states the GUI HTML routes are unauthenticated and rely on browser cookie inspection.
- `gui_legacy_routes.py:63-78` serves `/gui`, `/console`, and `/trading` without `Depends(current_actor)`.
- `main_legacy.py:367-379` blocks unauthenticated access to non-exempt `/static/*` assets.
- `console.html:6-8` and `trading.html:6-9` load `/static/common.js` for the shared auth helper.
- `common.js:23-58` implements the async redirect check, but it cannot run if the static middleware returned 401 for the script.

Impact:

Unauthenticated users can receive dashboard HTML and see the console/trading shell instead of being server-side redirected or denied. Most JSON data routes remain protected, so this is primarily a UI boundary and information-disclosure issue, but it also makes auth behavior inconsistent and brittle.

Trigger:

Request `/console` or `/trading` without a valid auth cookie. The HTML is served, while `/static/common.js` is denied.

Recommended fix:

Guard all dashboard HTML routes server-side with `current_actor`, except `/login`. Alternatively put a small inline auth check in every unguarded HTML page and exempt only that minimal JS, but server-side denial is simpler and less brittle.

Verification:

Static trace only.

### DAPI-005

Severity: P2
Status: open
Area: Unauthenticated health/DB metadata
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/system_legacy_routes.py`

Summary:

`GET /api/v1/health/db` is unauthenticated and returns PostgreSQL pool stats plus raw probe exception text.

Evidence:

- `system_legacy_routes.py:195-199` defines the DB health endpoint without `Depends(current_actor)`.
- `system_legacy_routes.py:209-221` returns `db_pool.pool_stats()` and `probe: str(exc)` on failure.
- `system_legacy_routes.py:225-236` separately defines a minimal unauthenticated `/api/v1/healthz` endpoint for liveness, so richer DB telemetry does not need to be public.

Impact:

Unauthenticated callers can enumerate DB availability and pool behavior, and failure messages may expose internal connection or schema details. This creates an unnecessary reconnaissance endpoint beyond the minimal liveness probe.

Trigger:

Call `/api/v1/health/db` without authentication.

Recommended fix:

Require authentication for `/api/v1/health/db` or return only a minimal public status. Keep detailed pool stats and exception text behind `current_actor` or an operator-only diagnostics scope.

Verification:

Static trace only.

### DAPI-006

Severity: P2
Status: open
Area: Inconsistent write-route authorization model
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main_legacy.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_legacy_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_write_routes.py`

Summary:

The codebase defines a scope-plus-operator-identity contract for every write operation, but many state-changing API routes use only `current_actor` and do not enforce a route-specific role, scope, or request-operator identity check.

Evidence:

- `auth.py:248-259` says every write operation should enforce both scope permission and operator identity via `require_scope_and_identity`.
- `main_legacy.py:389-418` authenticates a token and returns a static configured actor.
- `control_legacy_routes.py:161-165` exposes scheduled restart with only `Depends(current_actor)`.
- `paper_trading_routes.py:197-304`, `paper_trading_routes.py:564-592`, and `paper_trading_routes.py:1053-1080` expose paper session, close, and config writes with only `Depends(current_actor)`.
- `risk_routes.py:215-235`, `risk_routes.py:252-264`, and `risk_routes.py:635-673` mutate risk config with only `Depends(current_actor)`; this overlaps with RC-003 and is included here as API-surface evidence.
- `strategy_write_routes.py:58-99` and `strategy_write_routes.py:102-186` mutate dynamic risk or strategy active state with only `Depends(current_actor)`.

Impact:

Authorization becomes endpoint-specific and easy to regress. Any token that passes authentication may be enough for operational mutations unless each handler manually remembers the right role/scope gate. The default static actor also ships with broad roles and scopes, so the distinction between viewer/operator/config-admin is weak unless every route enforces it.

Trigger:

Use a valid bearer token or GUI cookie against one of the listed write endpoints, regardless of intended scope separation.

Recommended fix:

Move write authorization into reusable FastAPI dependencies such as `Depends(require_scope("paper:trade"))`, `Depends(require_operator)`, and `Depends(require_scope("input:config"))`. For routes without `RequestEnvelope`, derive actor id server-side and audit it explicitly; do not rely on client-provided `updated_by` or omitted envelope identity.

Verification:

Static trace only.

### DAPI-007

Severity: P2
Status: open
Area: API-side scheduled restart process control
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_legacy_routes.py`
- `helper_scripts/restart_all.sh`

Summary:

`POST /api/v1/system/scheduled-restart` kills only the handling process PID and launches a standalone `python -m uvicorn` command, bypassing the normal restart script, worker count, service manager, database/env setup, and watchdog maintenance semantics.

Evidence:

- `control_legacy_routes.py:117-130` builds a temporary shell script using `os.getpid()`, `kill {pid}`, and `nohup {python} -m uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- `control_legacy_routes.py:133-143` launches that script with `subprocess.Popen`.
- `control_legacy_routes.py:161-165` exposes the endpoint with only authentication.
- `restart_all.sh:33` defaults API workers to `OPENCLAW_API_WORKERS` or `4`.
- `restart_all.sh:275-279` starts the API through the configured venv, database URL, IPC secret, log path, and worker count.

Impact:

In the default multi-worker deployment, the endpoint can kill only one worker while the uvicorn parent continues and may spawn a replacement. The temporary script can then start an unmanaged second server or fail to bind the port. Even in single-worker mode, it may lose required environment, worker count, logging, and service-manager behavior.

Trigger:

Call `POST /api/v1/system/scheduled-restart` from any API worker, especially under `uvicorn --workers 4`.

Recommended fix:

Remove in-process shell-script restart from the HTTP API or replace it with a narrow operator-only request that writes an intent for the service manager/watchdog to execute. If kept, route through `restart_all.sh --api-only` or launchd/systemd and enforce maintenance/locking semantics.

Verification:

Static trace only.

## Controls Confirmed

- Most primary JSON/data routes require `current_actor`, and many newer write routes add explicit operator-role checks.
- Legacy control operations that accept `RequestEnvelope` generally use `require_scope_and_identity` inside `control_ops.py` and `pnl_ops.py`.
- CORS strips wildcard origins when credentials are enabled.
- Static assets under `/static` are protected by middleware, except the small login-required exemption list.
- Settings API key write endpoints whitelist slots, validate Bybit credentials before persistence, restrict file permissions, and require operator auth.
- OpenClaw gateway proxy requires authentication and strips the `Authorization` header, but DAPI-003 notes the remaining cookie leak.

## Residual Risk

This segment was a static route and code audit. It did not enumerate the live FastAPI route table at runtime, test browser behavior, send real HTTP requests, or verify deployed reverse-proxy/CORS settings. Runtime validation should include an unauthenticated request sweep for every route and a multi-worker scheduled-restart smoke test before remediation is considered complete.
