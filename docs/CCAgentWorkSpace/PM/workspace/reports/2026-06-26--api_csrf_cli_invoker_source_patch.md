# PM Report - API CSRF CLI Invoker Source Patch

Date: 2026-06-26

## Status

`DONE_WITH_CONCERNS`

Active blocker:

`P1-RUNTIME-HEALTH-HYGIENE-API-CSRF-CLI-INVOKER`

Next blocker after operator-requested pause:

`P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-ACTION-E3-BB-REVIEW`

## Session State

- Session state: `/tmp/openclaw/session_loop_state_20260626T020500Z_api_csrf_cli_invoker.json`
- Session packet: `/tmp/openclaw/session_loop_state_packet_20260626T020500Z_api_csrf_cli_invoker.json`
- Anti-repeat decision: source-only progress was allowed because the prior cleanup action had new runtime evidence, a concrete CSRF blocker, and an executable narrow source/read-only checkpoint.

## What Changed

Added `helper_scripts/operator/control_api_csrf_post.py`, a secret-safe wrapper for CSRF-protected control API POSTs.

Key boundaries:

- Uses a `0600` temporary curl config so the Bearer token is not passed through argv.
- Reads the API token only from `OPENCLAW_API_TOKEN` or a token file; there is no `--api-token` argv option.
- Uses curl's cookie engine with `cookie = "oc_csrf=..."` plus `X-CSRF-Token`.
- Does not use a raw `Cookie:` header.
- Allows only approved token-bearing API bases: `http://100.91.109.86:8000`, `http://127.0.0.1:8000`, and `http://localhost:8000`.
- Rejects `--api-base` values with userinfo, path, query, or fragment.
- Rejects path bypass shapes: query, fragment, percent encoding, dot segments, empty path segments, backslash, URL schemes, and whitespace.
- Allows default non-reviewed POSTs only for `/api/v1/__csrf_probe_*` no-route probes.
- Requires exact reviewed write binding for any real POST path.
- Requires exact reviewed mutation binding for exchange/session-sensitive paths such as `/api/v1/strategy/demo/session/stop`, demo positions paths, and live paths.
- Treats unexpected non-2xx HTTP responses as process failure unless explicitly allowed with `--expect-http`.

Updated:

- `helper_scripts/operator/test_control_api_csrf_post.py`
- `helper_scripts/SCRIPT_INDEX.md`
- `TODO.md`
- `docs/CLAUDE_CHANGELOG.md`

## Review Notes

PA and E2 initially raised concerns around default allow breadth, query-string bypass, HTTP non-2xx success handling, argv token leakage, and denylist fail-open behavior. Those were fixed by:

- Making all real POST paths reviewed-write gated.
- Adding exact sensitive-path reviewed-mutation gates.
- Removing `--api-token`.
- Adding default HTTP 2xx-only success with explicit `--expect-http` override.
- Rejecting query strings and fragments.

E2's second review raised two remaining high-risk bypasses:

- Probe-prefix path normalization via dot segments.
- Arbitrary `--api-base` token exfiltration.

Both were fixed before this checkpoint by rejecting dot/encoded/empty/backslash path bypasses and adding an approved control-plane API base allowlist. E4 verified the focused tests, `py_compile`, and `git diff --check`.

## Verification

Local source verification:

```bash
python3 -m pytest -q helper_scripts/operator/test_control_api_csrf_post.py
# 16 passed

python3 -m py_compile helper_scripts/operator/control_api_csrf_post.py helper_scripts/operator/test_control_api_csrf_post.py

git diff --check
```

Non-exchange runtime probe:

```bash
python3 helper_scripts/operator/control_api_csrf_post.py \
  --api-base http://100.91.109.86:8000 \
  --path /api/v1/__csrf_probe_no_route \
  --token-file program_code/exchange_connectors/bybit_connector/control_api_v1/.secrets/api_token \
  --output /tmp/openclaw/control_api_csrf_helper_no_route_probe_final_after_e2.json \
  --expect-http 404
```

Result summary:

- `ok=true`
- `http_status=404`
- `http_status_ok=true`
- `uses_curl_cookie_engine=true`
- `uses_raw_cookie_header=false`

Dry-run sensitive path check:

```bash
python3 helper_scripts/operator/control_api_csrf_post.py \
  --path /api/v1/strategy/demo/session/stop \
  --token-file program_code/exchange_connectors/bybit_connector/control_api_v1/.secrets/api_token \
  --output /tmp/openclaw/control_api_csrf_helper_stop_dry_run_final.json \
  --dry-run \
  --allow-reviewed-write reviewed_pm_control_api_write \
  --allow-reviewed-mutation reviewed_e3_bb_pm_exchange_mutation \
  --reviewed-path /api/v1/strategy/demo/session/stop \
  --reviewed-change-id pm-e3-bb-20260626-csrf-helper-final
```

Result summary:

- `ok=true`
- `dry_run=true`
- `sensitive_path=true`
- `uses_curl_cookie_engine=true`
- `uses_raw_cookie_header=false`

Negative sensitive path check without reviewed mutation returned `ok=false` and exit code `2`.

## Boundaries Preserved

This checkpoint did not:

- Retry `/api/v1/strategy/demo/session/stop` as a real POST.
- Call Bybit POST/cancel/modify/close/order endpoints.
- Write PG or change schema.
- Sync source to Linux runtime.
- Restart/rebuild services.
- Edit crontab or runtime env.
- Enable Rust writer or adapter.
- Lower global Cost Gate.
- Grant probe/order/live authority.
- Claim profitability or bounded-probe proof.

## Remaining Concern

The helper is source-only on Mac/origin until a separate runtime/source-sync review. Actual residual exposure cleanup still requires a fresh `PM -> E3 -> BB -> PM` action envelope with a fresh pre-action inventory and a hard stop on any auth/CSRF/runtime failure.
