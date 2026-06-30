# 2026-07-01 Operator Brief — GUI One-Shot Fanout Budget Guard

PM added a static efficiency guard for the Stock/ETF GUI one-shot load path.

What changed:

- `tab-stock-etf.js` may only have one `Promise.all` and one
  `waitForServerUp(loadReadiness)`.
- The Stock/ETF GUI fanout is fixed at 16 `ocApi` calls.
- Every `ocApi` call must be GET-only with `timeoutMs: 5000` and
  `toastOnError: false`.

Verification passed:

- Python no-write static guard: `21 passed`
- Full Stock/ETF FastAPI/static: `120 passed`
- IBKR timeline + trace-title guard: `2 passed`
- `git diff --check`: PASS

Boundary unchanged: no endpoint/IPC method change, client input change, IBKR
contact, SDK import, socket/HTTP, secret access, connector runtime, read probe
execution, paper order/cancel/replace, fill import, DB/evidence writer,
tiny-live/live authority, Linux runtime sync/restart, or Bybit behavior change.
