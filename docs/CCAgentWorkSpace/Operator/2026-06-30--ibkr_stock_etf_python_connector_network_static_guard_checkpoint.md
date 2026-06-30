# Operator Brief - IBKR Stock/ETF Python Connector Network Static Guard

Date: 2026-06-30

## Summary

PM tightened the source-only Python guard for the IBKR Stock/ETF connector
skeleton. The guard now blocks network-client imports and dynamic imports in the
Stock/ETF / IBKR Python surface.

Covered forbidden modules:

- `socket`
- `http.client`
- `requests`
- `httpx`
- `urllib`
- `urllib3`
- `aiohttp`
- `websocket`
- `websockets`

This applies only to Stock/ETF / IBKR Python files and the inert IBKR connector
skeleton. Existing Bybit connector modules are not scanned or changed.

## Verification

- Python no-write static guard: `4 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`: PASS

## Boundary

No IBKR contact, SDK import, socket/HTTP, secret access/creation, connector
runtime, read probe execution, paper order/cancel/replace, fill import, evidence
writer, DB apply, evidence clock, tiny-live/live authority, or Bybit behavior
change.
