# PM Checkpoint - IBKR Stock/ETF Rust Feature Flag Env Allowlist Guard

Date: 2026-07-01

Scope: Stock/ETF Rust feature flag acceptance test only.

## Outcome

PM added an acceptance regression proving `StockEtfFeatureFlags::from_lookup`
queries exactly five non-secret feature flag keys and returns default-off flags
when all keys are absent.

## Guards

- Exact lookup order is locked for lane enabled, IBKR readonly enabled, IBKR
  paper enabled, asset-lane default, and Stock/ETF shadow-only.
- The allowlist rejects secret/token/password/account/key-bearing env names.
- The absent-key path must equal `StockEtfFeatureFlags::default()`.

## Verification

- File-scoped `rustfmt --check`: PASS.
- `stock_etf_lane_acceptance`: `9 passed`.
- IBKR timeline + trace-title structure guard: `2 passed`.
- Full Stock/ETF FastAPI/static: `112 passed`.
- `git diff --check`: PASS.

Workspace-wide `cargo fmt --all -- --check` is blocked by pre-existing unrelated
Rust formatting drift outside this IBKR slice.

## Boundary

No production Rust behavior change, endpoint, IPC method, client input, IBKR
contact, SDK import, socket/HTTP, connector runtime, secret access, read probe
execution, paper order, fill import, evidence writer, DB apply, evidence clock,
tiny-live, live, or Bybit behavior change.
