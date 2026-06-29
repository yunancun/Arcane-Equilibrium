# Control API OpenAPI Schema Runtime Fix

Date: 2026-06-29
Owner: PM
Status: DONE_WITH_CONCERNS

## What changed

The Control API `/openapi.json` 500 is fixed. The cause was a FastAPI/Pydantic forward-reference issue in the replay advisory route on the Linux runtime package versions. Source commit `d9c25fe1` removes the postponed annotations from that route and adds an OpenAPI regression test.

## Verified

- Runtime source synced and clean on `main...origin/main`
- Runtime replay advisory tests: `4 passed`
- Runtime full app OpenAPI generation: `FULL_OPENAPI_OK 288`
- HTTP `/openapi.json`: `200`, OpenAPI `3.1.0`, `288` paths
- API user unit active at MainPID `982147`
- Engine PID `877736` stayed alive; Demo-only env unchanged

## Still blocked

Bounded Demo execution is still blocked by the Demo API slot mismatch and read-only connector mode. The correct key-entry endpoint is parameterized:

`POST /api/v1/settings/api-key/{slot}` with `{slot}=demo`

No secret/env mutation, Bybit private call, Decision Lease, order, Cost Gate change, or live/mainnet action was performed.
