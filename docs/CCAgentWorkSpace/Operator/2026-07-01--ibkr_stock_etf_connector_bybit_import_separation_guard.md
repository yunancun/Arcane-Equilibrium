# 2026-07-01 Operator Brief — IBKR Connector Bybit Import Separation Guard

PM added a source-only guard to keep the IBKR connector skeleton separate from
Bybit runtime/control-api modules.

What changed:

- New AST test scans `program_code/broker_connectors/ibkr_connector/**/*.py`.
- It blocks direct imports of Bybit connector/control-api module prefixes.
- It also blocks literal dynamic imports via `__import__` and
  `importlib.import_module`.
- Existing display payload field `bybit_path_reused=false` remains; code-path
  reuse is the prohibited part.

Verification passed:

- Python compile: PASS
- Connector skeleton tests: `6 passed`
- Python no-write static guard: `17 passed`
- Full Stock/ETF FastAPI/static: `114 passed`
- IBKR timeline + trace-title guard: `2 passed`
- `git diff --check`: PASS

Boundary unchanged: no IBKR contact, SDK import, socket/HTTP, secret access,
connector runtime, read probe execution, paper order, fill import, DB/evidence
writer, tiny-live/live authority, Linux runtime sync/restart, or Bybit behavior
change.
