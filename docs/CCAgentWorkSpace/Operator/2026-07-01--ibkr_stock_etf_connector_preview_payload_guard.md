# 2026-07-01 Operator Brief — IBKR Connector Preview Payload Guard

PM tightened the inert IBKR connector skeleton preview contract.

What changed:

- `connection_plan()` now returns an explicitly blocked preview:
  `surface_id`, `accepted=false`, `status=blocked_source_only`,
  `phase2_gate_not_accepted`, and `connection_plan_blocked`.
- New tests lock exact payload shapes for connection plan, readiness, account,
  market-data, contract-detail, paper lifecycle, fill-import, and fixture
  previews.
- The tests keep every preview no-network, no-secret, no paper/live channel,
  no broker write, no DB apply, and no Bybit path reuse.

Verification passed:

- Python compile: PASS
- Connector skeleton tests: `5 passed`
- Python no-write static guard: `17 passed`
- Full Stock/ETF FastAPI/static: `113 passed`
- IBKR timeline + trace-title guard: `2 passed`
- `git diff --check`: PASS

Boundary unchanged: no IBKR contact, SDK import, socket/HTTP, secret access,
connector runtime, read probe execution, paper order, fill import, DB/evidence
writer, tiny-live/live authority, Linux runtime sync/restart, or Bybit behavior
change.
