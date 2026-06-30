# 2026-07-01 Operator Brief - IBKR Stock/ETF Python Secret/Env Access Static Guard

PM completed a source-only Python boundary checkpoint for Stock/ETF / IBKR
secret and environment material access.

- New AST guard scans Stock/ETF FastAPI routes, Stock/ETF normalizers, and the
  inert IBKR connector skeleton.
- The guard blocks env/secret helper imports and calls such as `os.environ`,
  `getenv` / `os.getenv`, `Path.home`, `expanduser`, `read_text`, `read_bytes`,
  and `open()`.
- Existing `secret_slot_contract` handling remains display-only schema
  normalization; it does not authorize reading secret material.

Verification passed:

- Python no-write static guard: `17 passed`
- Route/no-write focused tests: `31 passed`
- Full Stock/ETF FastAPI/static: `112 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- `git diff --check`

Boundary unchanged: no IBKR contact, no broker SDK/network client, no connector
runtime, no secret access, no read probe execution, no paper order, no DB/evidence
writer, no tiny-live/live authority, and no Bybit behavior change.
