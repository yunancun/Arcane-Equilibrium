# 2026-07-01 Operator Brief — GUI Background Work Static Guard

PM added a static guard keeping the Stock/ETF GUI display surface free of
polling, push channels, workers, and high-frequency timing.

What changed:

- Static scan covers `tab-stock-etf*.js` and `tab-stock-etf.html`.
- It blocks intervals, timeouts, animation/idle callbacks, WebSocket, SSE,
  workers, BroadcastChannel, XMLHttpRequest, sendBeacon, `performance.now`, and
  `Date.now`.
- The existing one-shot authenticated GET load path remains allowed.

Verification passed:

- Python no-write static guard: `20 passed`
- Full Stock/ETF FastAPI/static: `119 passed`
- IBKR timeline + trace-title guard: `2 passed`
- `git diff --check`: PASS

Boundary unchanged: no endpoint/IPC method change, client input change, IBKR
contact, SDK import, socket/HTTP, secret access, connector runtime, read probe
execution, paper order/cancel/replace, fill import, DB/evidence writer,
tiny-live/live authority, Linux runtime sync/restart, or Bybit behavior change.
