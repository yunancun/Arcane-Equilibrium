# PM Checkpoint - IBKR Stock/ETF Python Secret/Env Access Static Guard

Date: 2026-07-01

Scope: Stock/ETF / IBKR Python source boundary only.

## Outcome

PM added an AST static guard proving scoped Stock/ETF / IBKR Python surfaces do
not import env/secret helper modules or read secret/environment material.

The guard scans the Stock/ETF FastAPI display routes, Stock/ETF normalizers, and
the inert `program_code/broker_connectors/ibkr_connector/` skeleton.

## Guards

- Forbids `os`, `dotenv`, `getpass`, and `keyring` imports in the scoped surface.
- Forbids `os.environ`, `getenv` / `os.getenv`, `getpass`, and `load_dotenv`.
- Forbids `Path.home`, `expanduser`, `read_text`, `read_bytes`, and any `open()`
  call.
- Keeps display-only `secret_slot_contract` schema normalization allowed, but
  blocks any material read path.

## Verification

- Python no-write static guard: `17 passed`.
- Route/no-write focused tests: `31 passed`.
- Full Stock/ETF FastAPI/static: `112 passed`.
- IBKR timeline + trace-title structure guard: `2 passed`.
- `git diff --check`: PASS.

## Boundary

No new endpoint, IPC method, client input, IBKR contact, SDK import,
socket/HTTP, connector runtime, secret access, read probe execution, paper
order, fill import, evidence writer, DB apply, evidence clock, tiny-live,
live, or Bybit behavior change.
