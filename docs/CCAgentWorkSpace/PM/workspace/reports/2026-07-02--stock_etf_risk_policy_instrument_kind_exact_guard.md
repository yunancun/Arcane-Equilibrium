# PM Report — Stock/ETF Risk Policy Instrument Kind Exact Guard

Date: 2026-07-02
Role: PM(default)
Scope: Test-only hardening for ADR-0048 Stock/ETF risk policy instrument-kind acceptance.

## Verdict

DONE_WITH_CONCERNS.

此 checkpoint 將 risk policy accepted fixture 的 `instrument_kinds_allowed` 與 `instrument_kinds_denied` 從局部 membership 檢查收緊為完整 ordered-vector coverage。

## Changes

- Replaced accepted fixture `instrument_kinds_allowed` membership assertions with a complete ordered vector assertion.
- Replaced accepted fixture `instrument_kinds_denied` membership assertions with a complete ordered vector assertion.
- Added a source guard rejecting `.instrument_kinds_allowed.contains(...)` and `.instrument_kinds_denied.contains(...)` before the guard.
- Kept `stock_etf_risk_policy_acceptance.rs` below 800 lines: 393 lines.

## Verification

- `PATH=... cargo fmt --manifest-path rust/Cargo.toml -p openclaw_types -- --check` — PASS.
- `PATH=... cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_risk_policy_acceptance` — 10 passed.
- `PATH=... cargo test --manifest-path rust/Cargo.toml -p openclaw_types` — PASS.
- `python3 -B -m pytest -q tests/structure/test_stock_etf_risk_policy_source_static.py --tb=short` — 7 passed.
- Risk policy instrument-kind no-loose assertion scan — PASS.
- `git diff --check` — PASS.

## Boundary

No Rust production code changed. No risk policy validator semantics, source/runtime config, Rust IPC handler behavior, FastAPI route behavior, GUI behavior, connector production code, IBKR contact, IBKR SDK import, socket/client construction, secret access or serialization, connector runtime, broker session, read-only probe execution, paper order routing/cancel/replace, fill import execution, release launch, DB/evidence writer, scorecard writer, evidence clock, paper-shadow launch, tiny-live/live authorization, Linux runtime sync/restart, destructive DB cleanup, or Bybit behavior changed.

Sub-agent note: no subagent was spawned because this was a narrow local test-only Rust acceptance hardening checkpoint with direct PM verification and no runtime or exchange-facing action. PM skipped PA/E1/E2/E4/QA for this checkpoint because the implementation was exact assertion hardening in one test file, not a behavior change.
