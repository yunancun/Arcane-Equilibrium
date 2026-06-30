# Operator Brief - IBKR Stock/ETF Python Persistence Static Guard

Date: 2026-06-30

## Summary

PM added a source-only AST guard for Stock/ETF / IBKR Python persistence and
file-writer boundaries.

- Scoped Stock/ETF / IBKR Python files may not import DB, persistence,
  object-store, or local evidence-writer modules.
- Dynamic persistence imports are blocked.
- Explicit file-writer calls such as `write_text`, `write_bytes`, write-mode
  `open(...)`, and `os.replace(...)` are blocked.

## Verification

- Python no-write static guard: `9 passed`
- Full Stock/ETF FastAPI/static: `103 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`: PASS

## Boundary

No IBKR contact, SDK import, socket/HTTP, secret access/creation, connector
runtime, read probe execution, paper order/cancel/replace, fill import, evidence
writer, DB apply, evidence clock, tiny-live/live authority, or Bybit behavior
change.
