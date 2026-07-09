# AgentTodo MAG-023 / MAG-025 Replay Proofs

Date: 2026-05-07
Role: PM + local E1/E4 fast path
Status: MAG-023 DONE; MAG-025 DONE

## Scope

Operator confirmed REF-21 replay is complete and asked to close the pending
AgentTodo M2 replay items:

- MAG-023 replay proof for active-position market data after scanner ranking drop.
- MAG-025 scanner churn replay fixture.

No runtime restart, deploy, DB migration, live auth, or strategy/risk config
change was requested or performed.

## Result

- Added `adapter_pipeline_preserves_open_position_tick_after_scanner_drop` in
  `rust/openclaw_engine/src/replay/runner.rs`.
  - The fixture has scanner timeline active on ETH only.
  - SOL has no open position and is skipped by the scanner timeline gate.
  - BTC has a seeded open position despite scanner removal, still receives its
    tick, emits a close fill, and realizes positive PnL.
- Added `replay_churn_fixture_identifies_scanner_driven_wave` in
  `rust/openclaw_engine/src/replay/scanner_timeline.rs`.
  - The synthetic fixture deterministically reconstructs a SOLUSDT -> XRPUSDT
    scanner wave.
  - Assertions cover `added`, `removed`, active symbols, and `is_active_at`.
- Updated `AgentTodo.md`:
  - MAG-023 -> DONE (MAC/LINUX REPLAY PROOF)
  - MAG-025 -> DONE (MAC/LINUX REPLAY FIXTURE)

## Verification

Mac clean detached worktree (`/tmp/tradebot_mag023_025_head`) against
`ed330937`:

- `cargo test -p openclaw_engine scanner_timeline --features replay_isolated`
- `cargo test -p openclaw_engine adapter_pipeline_preserves_open_position_tick_after_scanner_drop --features replay_isolated`

Mac current dirty worktree smoke:

- same two targeted Rust commands passed before staging the clean patch.

Linux clean detached worktree (`/tmp/tradebot_mag023_025_head`) against
`ed330937`:

- `cargo test -p openclaw_engine scanner_timeline --features replay_isolated`
- `cargo test -p openclaw_engine adapter_pipeline_preserves_open_position_tick_after_scanner_drop --features replay_isolated`

## Drift Note

During local work, the Mac main worktree gained a separate uncommitted
replay/calibration patch set across 27 files while Linux remained clean. The
MAG-023/MAG-025 source patch was therefore rebuilt and tested in a clean
detached worktree, then staged as a narrow patch so unrelated replay changes
are not committed by this batch.
