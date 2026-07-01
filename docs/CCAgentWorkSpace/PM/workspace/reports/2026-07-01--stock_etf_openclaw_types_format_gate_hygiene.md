# 2026-07-01 — Stock/ETF Openclaw Types Format Gate Hygiene

## Scope

PM cleared the pre-existing `openclaw_types` package formatting blocker that had forced recent
Stock/ETF Rust checkpoints to use file-scoped rustfmt verification.

The only source change is mechanical rustfmt output in
`rust/openclaw_types/src/risk.rs`. This is not a logic change, not an IBKR behavior change, not a
Bybit behavior change, and not a runtime/deploy action.

## Change

- Ran `rustfmt rust/openclaw_types/src/risk.rs`.
- The diff only changes formatting of one `return Err(...)` expression and two vector literals in
  tests.
- This restores `cargo fmt -p openclaw_types -- --check` as a usable package-level gate for
  subsequent IBKR/Stock-ETF Rust checkpoints.

## Verification

- `cargo fmt -p openclaw_types -- --check`: PASS.
- `cargo test -p openclaw_types risk --lib`: `13 passed`.
- Full `cargo test -p openclaw_types`: PASS.
- Dynamic docs trace pytest: `2 passed, 5 deselected`; parsed checkpoint titles `132`,
  missing `[]`.
- Diff check: PASS.

## Boundary

No trading logic, risk semantics, endpoint, IPC method, connector, SDK import, socket/HTTP path,
secret access, read-only probe execution, result import, DB/evidence writer, paper order route,
tiny-live/live authorization, Linux runtime sync/restart, or Bybit live/demo execution behavior
changed.
