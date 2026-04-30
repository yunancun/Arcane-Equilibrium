# Maintenance Warning-Zone Split — 2026-04-30

## Result

Completed the requested TODO items 1-4 and updated `TODO.md`.

- Rust `helpers.rs` split: 1411 -> 336 LOC, tests moved to sibling.
- `ai_service_dispatch.py` split: Guardian handler/parser moved to sibling.
- G3-07 env resolution aligned with explicit URL override, legacy env override, file-based `bybit_endpoint`, then safe demo fallback.
- `checks_derived.py` and `ipc_client.py` warning-zone splits completed with compatible imports.

## Verification

- Python compile: PASS.
- Layer2 / IPC / AIService / H-state / healthcheck targeted tests: PASS.
- Rust fmt + PHYS-LOCK helper tests: PASS.
- `git diff --check`: PASS.

## Runtime Boundary

No deploy, rebuild, restart, live authorization, or runtime config change was performed.
