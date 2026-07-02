# PM Report — Stock/ETF Broker Capability Gate Matrix Exact Guard

Date: 2026-07-02
Role: PM(default)
Scope: Test-only hardening for ADR-0048 Stock/ETF broker capability registry operation gate acceptance.

## Verdict

DONE_WITH_CONCERNS.

This checkpoint adds exact ordered-vector coverage for every accepted broker
capability operation's `required_gates` matrix.

## Changes

- Added `stock_etf_broker_capability_registry_gate_matrix_acceptance.rs` to pin
  complete ordered gate vectors for all 15 accepted broker operations.
- The new matrix guard also pins authority scope, typed denial reason, Rust
  ownership, audit-event requirement, and source-artifact-hash requirement.
- Removed positive `.required_gates.contains(...)` membership assertions from
  `stock_etf_broker_capability_registry_acceptance.rs` for accepted rows and
  paper-fill-import paths.
- Added a source guard that rejects `.required_gates.contains(...)` in the
  legacy broker capability registry acceptance file.
- Kept test file sizes below the 800-line review threshold: legacy acceptance
  607 lines; gate matrix acceptance 237 lines.

## Verification

- `PATH=/Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH /Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/cargo fmt --manifest-path rust/Cargo.toml -p openclaw_types -- --check` — PASS.
- `PATH=/Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH /Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_broker_capability_registry_acceptance --test stock_etf_broker_capability_registry_gate_matrix_acceptance -- --nocapture` — 14 + 2 passed.
- `PATH=/Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH /Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/cargo test --manifest-path rust/Cargo.toml -p openclaw_types -- --nocapture` — PASS.
- `python3 -B -m pytest -q tests/structure/test_stock_etf_broker_capability_registry_source_static.py --tb=short` — 9 passed.
- Broker capability gate no-loose assertion scan — PASS.
- `git diff --check` — PASS.

## Boundary

No Rust production code changed. No broker capability validator semantics, Rust
IPC handler behavior, FastAPI route behavior, GUI behavior, connector
production code, IBKR contact, IBKR SDK import, socket/client construction,
secret access or serialization, connector runtime, broker session, read-only
probe execution, paper order routing/cancel/replace, fill import execution,
release launch, DB/evidence writer, scorecard writer, evidence clock,
paper-shadow launch, tiny-live/live authorization, Linux runtime sync/restart,
destructive DB cleanup, or Bybit behavior changed.

Sub-agent note: no subagent was spawned because this was a narrow local
test-only Rust acceptance hardening checkpoint with direct PM verification and
no runtime or exchange-facing action. PM skipped PA/E1/E2/E4/QA for this
checkpoint because the implementation was a split assertion relocation plus
focused source/test verification, not a behavior change.
