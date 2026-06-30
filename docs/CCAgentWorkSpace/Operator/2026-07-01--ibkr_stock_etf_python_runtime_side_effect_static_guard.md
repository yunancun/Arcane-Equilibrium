# 2026-07-01 Operator Brief — Python Runtime Side-Effect Static Guard

PM added a source-only guard keeping the Stock/ETF / IBKR Python surface free of
clock, concurrency, and subprocess side effects.

What changed:

- Scoped Stock/ETF FastAPI routes/normalizers and the inert IBKR connector
  skeleton may not import `time`, `datetime`, `asyncio`, `threading`,
  `multiprocessing`, `subprocess`, or `concurrent`.
- The same scope may not call timing or background-work primitives such as
  `sleep`, `time`, `monotonic`, `perf_counter`, `now`, `Thread`, `Process`,
  `Popen`, `asyncio.run`, `create_task`, or `to_thread`.
- Existing Bybit runtime modules are outside this scan.

Verification passed:

- Python no-write static guard: `19 passed`
- Connector skeleton focused tests: `8 passed`
- Full Stock/ETF FastAPI/static: `118 passed`
- IBKR timeline + trace-title guard: `2 passed`
- `git diff --check`: PASS

Boundary unchanged: no endpoint/IPC method change, IBKR contact, SDK import,
socket/HTTP, secret access, connector runtime, read probe execution, paper
order/cancel/replace, fill import, DB/evidence writer, tiny-live/live authority,
Linux runtime sync/restart, or Bybit behavior change.
