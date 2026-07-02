# PM Report — Stock/ETF Rust IPC Fixture Split Guard

Date: 2026-07-02
Role: PM(default)
Scope: Hygiene-only/test-only split for Rust Stock/ETF IPC fixture tests.

## Verdict

DONE_WITH_CONCERNS.

This checkpoint reduces review and maintenance risk by splitting oversized
Stock/ETF Rust IPC fixture tests into smaller modules without changing handler
behavior, route behavior, runtime authority, or expected JSON semantics.

## Changes

- Kept `stock_etf.rs` as the parent module shell with the untrusted params test,
  exact assertion source guard, and shared dispatch/assertion helpers.
- Added `core_status_fixtures.rs` for Phase0, lane, evidence, universe, shadow,
  and paper status fixture tests.
- Added `phase5_status_fixtures.rs` for launch, release-packet, and
  disable-cleanup status fixture tests.
- Left `status_fixtures.rs` focused on account, reconciliation, and scorecard
  status fixture tests.
- Extended the Rust exact assertion source guard to cover the new modules.

## Verification

- Stock/ETF Rust IPC fixture line counts are all below 800 lines:
  `stock_etf.rs` 127, `core_status_fixtures.rs` 759,
  `status_fixtures.rs` 571, `phase5_status_fixtures.rs` 308.
- `/opt/homebrew/Cellar/rustup/1.29.0_2/bin/rustfmt --edition 2021 --check ...` — PASS.
- `RUSTC=/Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/rustc /Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/cargo test -p openclaw_engine stock_etf -- --test-threads=1` — PASS; Stock/ETF Rust IPC/lib 32 passed, other targets filtered and exited 0.
- Rust IPC fixture no-loose blocker assertion scan — PASS.

## Boundary

No Rust IPC handler behavior changed. No FastAPI route behavior, GUI behavior,
connector production code, IBKR contact, IBKR SDK import, socket/client
construction, secret access or serialization, connector runtime, broker session,
read-only probe execution, paper order routing/cancel/replace, release launch,
DB/evidence writer, scorecard writer, evidence clock, paper-shadow launch,
tiny-live/live authorization, Linux runtime sync/restart, destructive DB
cleanup, or Bybit behavior changed.

Sub-agent note: no subagent was spawned because the available tool policy only
permits spawning when the operator explicitly requests subagents/parallel agent
work. This was a narrow Rust fixture hygiene checkpoint verified locally with
focused Rust checks.
