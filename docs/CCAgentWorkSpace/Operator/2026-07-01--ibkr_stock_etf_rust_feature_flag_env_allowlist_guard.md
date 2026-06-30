# 2026-07-01 Operator Brief - IBKR Stock/ETF Rust Feature Flag Env Allowlist Guard

PM completed a source-only Rust feature flag contract checkpoint for Stock/ETF /
IBKR env lookup.

- `StockEtfFeatureFlags::from_lookup` now has an acceptance test for its exact
  five-key allowlist.
- The allowlist contains only non-secret feature flag names and explicitly
  rejects secret/token/password/account/key-bearing names.
- With all keys absent, the result must stay `StockEtfFeatureFlags::default()`.

Verification passed:

- File-scoped `rustfmt --check`
- `stock_etf_lane_acceptance`: `9 passed`
- IBKR timeline + trace-title structure guard: `2 passed`
- Full Stock/ETF FastAPI/static: `112 passed`
- `git diff --check`

Workspace-wide `cargo fmt --all -- --check` remains blocked by pre-existing
unrelated Rust formatting drift outside this IBKR slice.

Boundary unchanged: no production Rust behavior change, no IBKR contact, no
broker SDK/network client, no connector runtime, no secret access, no read probe
execution, no paper order, no DB/evidence writer, no tiny-live/live authority,
and no Bybit behavior change.
