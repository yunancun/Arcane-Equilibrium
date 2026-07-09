# W-AUDIT-5 F-12 True Runner Split Checkpoint

Date: 2026-05-09
Scope: source/test only
Runtime impact: no rebuild, no restart, no DB write, no live auth mutation

## Summary

This checkpoint closes the E5-verified F-12 path mismatch. The earlier split
changed `rust/openclaw_engine/src/bin/replay_runner.rs`, but the original
governance finding was the library runner at
`rust/openclaw_engine/src/replay/runner.rs`.

## Changes

- Split module-internal tests from `rust/openclaw_engine/src/replay/runner.rs`
  into sibling `rust/openclaw_engine/src/replay/runner_tests.rs`.
- Kept the test module as a child of `runner.rs` through
  `#[path = "runner_tests.rs"] mod runner_tests;`, preserving access to parent
  private helpers without changing production logic.
- Extended `tests/structure/test_replay_runner_split_static.py` so both
  `runner.rs` and `runner_tests.rs` are guarded below the 2000 LOC cap.
- Updated TODO and repo-synced Codex memory to mark `P2-AUDIT-VERIFY-2` done.

## LOC Result

- `rust/openclaw_engine/src/replay/runner.rs`: 2469 -> 1166 LOC
- `rust/openclaw_engine/src/replay/runner_tests.rs`: 1299 LOC

## Verification

- `cargo fmt --all --check`
- `python3 -m pytest -q tests/structure/test_replay_runner_split_static.py`
- `cargo test -p openclaw_engine --lib replay::runner -- --nocapture`
- `cargo test -p openclaw_engine --features replay_isolated --test replay_runner_e2e -- --nocapture`
- `cargo test -p openclaw_engine --features replay_isolated --test replay_runner_e2e_param_delta -- --nocapture`
- `git diff --check`

The replay integration tests still emit existing Rust unused warnings from
unrelated modules under the `replay_isolated` feature build. No new warning type
was introduced by this split.

## Remaining W-AUDIT-5 Work

- F-20 damaged table dump/drop remains an ops task requiring NAS dump and
  explicit destructive DB authorization.
- Canonical / signature / hash JSON paths remain on stdlib until byte-contract
  tests exist.
