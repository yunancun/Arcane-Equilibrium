# 2026-07-01 Operator Brief — FastAPI IBKR Connector Runtime Wiring Guard

PM added a source-only guard that prevents Stock/ETF FastAPI/control-api
production code from importing the inert IBKR connector skeleton before runtime
approval.

What changed:

- New no-write static guard scans `control_api_v1/app` Stock/ETF / IBKR Python
  files.
- It blocks direct and literal dynamic imports of the IBKR connector skeleton.
- Skeleton tests may still import the package; production route/normalizer code
  may not.
- This keeps the connector package source-only and avoids startup/runtime
  coupling.

Verification passed:

- Python no-write static guard: `18 passed`
- Connector skeleton tests: `6 passed`
- Full Stock/ETF FastAPI/static: `115 passed`
- IBKR timeline + trace-title guard: `2 passed`
- `git diff --check`: PASS

Boundary unchanged: no IBKR contact, SDK import, socket/HTTP, secret access,
connector runtime, read probe execution, paper order, fill import, DB/evidence
writer, tiny-live/live authority, Linux runtime sync/restart, or Bybit behavior
change.
