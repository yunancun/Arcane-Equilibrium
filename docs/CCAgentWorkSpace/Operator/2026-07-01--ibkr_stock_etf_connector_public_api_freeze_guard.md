# 2026-07-01 Operator Brief — IBKR Connector Public API Freeze Guard

PM added a source-only public API freeze for the inert IBKR connector skeleton.

What changed:

- The connector package export list is exact and only exposes source-boundary
  types.
- `IbkrReadOnlyClient` only exposes read-only/display preview methods.
- `IbkrPaperClientBoundary` only exposes lifecycle and fill-import readiness
  descriptors.
- This prevents runtime-start, order-write, secret/network, or Bybit-reuse
  entrypoints from appearing under new public names before approval.

Verification passed:

- Connector skeleton focused tests: `8 passed`
- Python no-write static guard: `18 passed`
- Full Stock/ETF FastAPI/static: `117 passed`
- IBKR timeline + trace-title guard: `2 passed`
- `git diff --check`: PASS

Boundary unchanged: no endpoint/IPC method change, IBKR contact, SDK import,
socket/HTTP, secret access, connector runtime, read probe execution, paper
order/cancel/replace, fill import, DB/evidence writer, tiny-live/live authority,
Linux runtime sync/restart, or Bybit behavior change.
