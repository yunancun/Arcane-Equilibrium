# E1 Report: WP-05 Security Hardening

Date: 2026-05-16
Task: E3-MED-2 (bind 0.0.0.0) + E3-MED-4 (API error leak)
Status: IMPL DONE, awaiting E2 review

## 1. Task Summary

Two security findings from the 12-agent audit:

- **E3-MED-2**: `start_local.sh:86` and `beta_quickstart.sh:78` bind uvicorn
  to `0.0.0.0` (all network interfaces), exposing the API to the LAN.
  Production `restart_all.sh` was already fixed via `api_bind_host.sh` +
  Tailscale auto-detect; these two dev/quickstart scripts remained unfixed.

- **E3-MED-4**: Unhandled `Exception` in FastAPI routes would produce a default
  500 response containing `str(exc)`, potentially leaking internal file paths,
  stack traces, or database schema details to API clients.

## 2. Changes

| File | Line(s) | Change |
|---|---|---|
| `control_api_v1/start_local.sh` | 86 | `--host 0.0.0.0` -> `--host 127.0.0.1` |
| `control_api_v1/scripts/beta_quickstart.sh` | 78 | `--host 0.0.0.0` -> `--host 127.0.0.1` |
| `control_api_v1/app/main_legacy.py` | 358-379 (new) | Global `Exception` handler with `OPENCLAW_DEBUG` gate |

## 3. Key Diff

### start_local.sh (line 86)
```diff
-    --host 0.0.0.0 \
+    --host 127.0.0.1 \
```

### beta_quickstart.sh (line 78)
```diff
-"$VENV/uvicorn" app.main:app --host 0.0.0.0 --port 8000
+"$VENV/uvicorn" app.main:app --host 127.0.0.1 --port 8000
```

### main_legacy.py (new lines 358-379)
```python
_OPENCLAW_DEBUG = os.getenv("OPENCLAW_DEBUG", "").strip() == "1"

@app.exception_handler(Exception)
async def _unhandled_exception_handler(request, exc):
    logger.error("Unhandled exception on %s %s: %s",
                 request.method, request.url.path, exc, exc_info=True)
    if _OPENCLAW_DEBUG:
        detail = {"reason_codes": ["internal_error"], "detail": str(exc)}
    else:
        detail = {"reason_codes": ["internal_error"], "detail": "Internal server error"}
    return JSONResponse(status_code=500, content={"detail": detail})
```

## 4. Governance Check

| Rule | Status |
|---|---|
| No `--host 0.0.0.0` in main source | PASS (grep returns 0) |
| `restart_all.sh` untouched | PASS |
| E3-LOW-1 (CSP unsafe-inline) not touched | PASS (explicitly P2 backlog) |
| main_legacy.py line count | 494 (well under 800 warning) |
| No hardcoded paths | PASS |
| Comment language = Chinese | PASS |

## 5. Verification

- `grep -rn "\-\-host 0\.0\.0\.0" srv/ --include="*.sh"` -> 0 hits (excluding .claude/worktrees)
- `python3 -c "from ...app import main_legacy"` -> import OK, `_OPENCLAW_DEBUG=False`
- Exception handler registered: `<class 'Exception'>: _unhandled_exception_handler`
- `python3 -m pytest tests/structure/ -x -q` -> 36 passed
- `python3 -m pytest tests/structure/test_new_vuln_3_4_security_static.py -x -q` -> 3 passed

## 6. Scope Not Touched

- Individual route handlers that already return `str(exc)` in their own
  try/except blocks (e.g., `scout_routes.py`, `replay_full_chain_routes.py`,
  `openclaw_routes.py`) -- these are per-route design choices, not unhandled
  exceptions. A separate audit pass could sanitize those individually.
- `restart_all.sh` -- already fixed, explicitly excluded from scope.
- CSP `unsafe-inline` (E3-LOW-1) -- explicitly deferred to P2 backlog.
