# PM Report — Stock/ETF Lane-Scoped IPC IO Matrix Exact Guard

Date: 2026-07-02
Role: PM(default)
Scope: Test-only hardening for ADR-0048 Stock/ETF lane-scoped IPC command IO acceptance.

## Verdict

DONE_WITH_CONCERNS.

This checkpoint adds exact ordered-vector coverage for every accepted
lane-scoped IPC command's `required_gates` and `required_request_fields`.

## Changes

- Added `stock_etf_lane_scoped_ipc_io_matrix_acceptance.rs` to pin the complete
  ordered IO matrix for all 20 accepted lane-scoped IPC commands.
- Removed positive gate/field membership assertions from
  `stock_etf_lane_scoped_ipc_acceptance.rs` for submit, preview, shadow, and
  readonly-probe paths.
- Added a source guard that rejects `.required_gates.contains(...)`,
  `assert_fields(...)`, and positive request-field contains checks in the
  legacy acceptance file.
- Kept test file sizes below the 800-line review threshold: legacy acceptance
  746 lines; IO matrix acceptance 348 lines.

## Verification

- `PATH=/Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH /Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/cargo fmt --manifest-path rust/Cargo.toml -p openclaw_types -- --check` — PASS.
- `PATH=/Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH /Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_lane_scoped_ipc_acceptance --test stock_etf_lane_scoped_ipc_io_matrix_acceptance -- --nocapture` — 12 + 2 passed.
- `PATH=/Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH /Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/cargo test --manifest-path rust/Cargo.toml -p openclaw_types -- --nocapture` — PASS.
- `python3 -B -m pytest -q tests/structure/test_stock_etf_lane_scoped_ipc_source_static.py --tb=short` — 7 passed.
- Lane-scoped IPC IO no-loose assertion scan — PASS.
- `git diff --check` — PASS.

## Boundary

No Rust production code changed. No Rust IPC handler behavior, FastAPI route
behavior, GUI behavior, connector production code, IBKR contact, IBKR SDK
import, socket/client construction, secret access or serialization, connector
runtime, broker session, read-only probe execution, paper order
routing/cancel/replace, release launch, DB/evidence writer, scorecard writer,
evidence clock, paper-shadow launch, tiny-live/live authorization, Linux runtime
sync/restart, destructive DB cleanup, or Bybit behavior changed.

Sub-agent note: no subagent was spawned because this was a narrow local
test-only Rust acceptance hardening checkpoint with direct PM verification and
no runtime or exchange-facing action.
