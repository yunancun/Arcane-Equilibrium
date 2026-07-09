# NEW-VULN-3/4 Cookie + Phase4 Checkpoint

Date: 2026-05-09
Scope: source/test only
Runtime impact: no rebuild, no restart, no live auth mutation

## Summary

This checkpoint closes `P2-AUDIT-VERIFY-7`.

NEW-VULN-3 is closed by making cookie Secure auto mode treat positive HTTPS
proxy hints as a fail-closed Secure-cookie signal even when
`OPENCLAW_TRUST_PROXY_HEADERS` is not configured. Direct HTTP spoofing of such
a hint can only make the cookie unusable over HTTP; it no longer creates a
future reverse-proxy fail-open window.

NEW-VULN-4 is closed by mounting the existing Phase4 router in Control API
`main.py`. The weekly-review approve/reject endpoints remain gated by
`require_scope_and_operator(actor, "learning:manage")`; they are now reachable
instead of defensive dead code.

## Changes

- `auth_routes_common.py`
  - Added HTTPS proxy hint detection for `X-Forwarded-Proto`,
    `X-Forwarded-Ssl`, and RFC `Forwarded: proto=https`.
  - Preserved explicit `OPENCLAW_COOKIE_SECURE=0` as an operator override.
- `main.py`
  - Includes `phase4_router`.
- `tests/structure/test_new_vuln_3_4_security_static.py`
  - Covers cookie Secure auto behavior and Phase4 router mount contract.

## Verification

- `python3 -m pytest -q tests/structure/test_new_vuln_3_4_security_static.py`
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_phase4_routes.py`
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth_routes_common.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/phase4_routes.py`
- `git diff --check`

No runtime reload was performed, so Linux source has the fix after sync but the
running API will not load it until the next authorized restart/rebuild.
