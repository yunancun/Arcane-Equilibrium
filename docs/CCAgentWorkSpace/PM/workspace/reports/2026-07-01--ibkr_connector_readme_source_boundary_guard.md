# 2026-07-01 — IBKR Connector README Source Boundary Guard

## Scope

PM added a source-only README posture guard for the inert IBKR connector skeleton.

This is not a connector behavior change, not an endpoint change, not IBKR contact, not secret
access, not paper order routing, and not a Bybit behavior change. It only locks the connector
package documentation so the source-only boundary cannot drift toward runtime-ready wording.

## Guard Added

- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`

The guard pins:

- `program_code/broker_connectors/ibkr_connector/README.md` states the package is not a runtime
  IBKR connector;
- allowed content remains limited to typed blocked readiness payloads, non-secret loopback endpoint
  descriptors, display-only previews, and static test fixtures;
- denied content includes IBKR SDK imports, socket/HTTP contact, secret/env credential fallback,
  broker write methods, paper order routing, fill-import side effects, DB writes, tiny-live, and live;
- the README does not claim runtime-ready, live-ready, paper-order-ready, or direct broker write
  method support.

## Verification

- Connector skeleton test py_compile: PASS.
- Focused connector skeleton pytest: `10 passed`.
- Docs PM trace tests: PASS.
- Diff check: PASS.

## Boundary

No IBKR SDK import, no socket/HTTP, no secret read or creation, no connector runtime, no read-only
probe, no result import, no DB apply, no paper order route, no tiny-live/live authorization, and no
Bybit live/demo execution change.
