# 2026-07-01 — Stock/ETF Paper Order Acceptance Authority Gate Hardening

## Scope

PM added Rust acceptance coverage for Stock/ETF paper order request authority/effect gates in
`rust/openclaw_types/tests/stock_etf_paper_order_request_acceptance.rs`.

This is test-only. It does not change production Rust code, IPC handlers, endpoints, connector
runtime, IBKR contact behavior, secret access, DB/evidence writers, paper order routing, Linux
runtime state, or Bybit behavior.

## Tests Added

The acceptance suite now directly covers:

- request-method surface mismatches for preview, submit, cancel, and replace requests, including
  operation, authority-scope, and effect-capability blockers;
- effect-capable submit request requirements for session attestation, scoped authorization,
  decision lease, Guardian state, lifecycle contract, broker capability registry, and audit event;
- preview request rejection when effect/lifecycle, broker-order, cancel, or replace fields pollute
  the read-only preview envelope.

## Verification

- Targeted Rust acceptance: `cargo test -p openclaw_types --test stock_etf_paper_order_request_acceptance`
  passed `11 passed`.
- Targeted rustfmt: `rustfmt rust/openclaw_types/tests/stock_etf_paper_order_request_acceptance.rs` PASS.
- Full `cargo fmt -p openclaw_types -- --check`: known pre-existing formatting drift remains in
  `rust/openclaw_types/src/risk.rs` outside this checkpoint.
- Dynamic docs trace pytest: `2 passed, 5 deselected`; parsed checkpoint titles `131`, missing `[]`.
- Diff check: PASS.

## Boundary

No production code, endpoint, IPC method, connector, SDK import, socket/HTTP path, secret access,
read-only probe execution, result import, DB/evidence writer, paper order/cancel/replace route,
tiny-live/live authorization, Linux runtime sync/restart, or Bybit live/demo execution behavior
changed.
