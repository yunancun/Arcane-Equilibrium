# AgentTodo MAG-024/MAG-026 Scanner Authority Shadow

Date: 2026-05-07
Scope: AgentTodo M2 Scanner Advisory Conversion
Status: DONE

## Summary

Completed MAG-026 first, then MAG-024 as requested.

MAG-026 adds a regression proving scanner removal of an open-position symbol is review evidence only: the emitted `OpportunityDecay` carries `position_review_required=true`, `position_review_input=true`, `auto_close_allowed=false`, and `close_dispatch_allowed=false`.

MAG-024 wires the MAG-020 authority-mode contract into runtime:

- `ScannerConfig` accepts `[authority].mode` with default `legacy_gate`.
- TickPipeline receives the scanner authority mode at bootstrap.
- `legacy_gate` preserves the prior scanner hot-path reject behavior.
- `advisory_shadow` / `advisory_enforced` record legacy would-block reasons in intent details without suppressing the open path.
- Scanner decay rows now preserve the active authority mode from scanner config.

## Files

- `rust/openclaw_engine/src/scanner/config.rs`
- `rust/openclaw_engine/src/scanner/advisory.rs`
- `rust/openclaw_engine/src/scanner/runner.rs`
- `rust/openclaw_engine/src/event_consumer/bootstrap.rs`
- `rust/openclaw_engine/src/tick_pipeline/mod.rs`
- `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs`
- `rust/openclaw_engine/src/tick_pipeline/tests/fast_track_reduce.rs`
- `docs/architecture/multi_agent_rework_2026-05-05/AgentTodo.md`

## Verification

Mac:

- `cargo test -p openclaw_engine scanner_removal_of_open_position_is_review_input_not_close_signal --features replay_isolated`
- `cargo test -p openclaw_engine scanner_authority --features replay_isolated`
- `cargo test -p openclaw_engine test_persist_intent_helper_records_scanner_opportunity_shadow_details --features replay_isolated`
- `cargo test -p openclaw_engine scanner::advisory --features replay_isolated`
- `cargo test -p openclaw_engine tick_pipeline::tests::fast_track_reduce --features replay_isolated`
- `cargo test -p openclaw_engine scanner::config --features replay_isolated`
- `cargo test -p openclaw_engine scanner_timeline --features replay_isolated`

Linux detached worktree:

- `cargo test -p openclaw_engine scanner::config --features replay_isolated`
- `cargo test -p openclaw_engine scanner::advisory --features replay_isolated`
- `cargo test -p openclaw_engine tick_pipeline::tests::fast_track_reduce --features replay_isolated`
- `cargo test -p openclaw_engine scanner_timeline --features replay_isolated`

## Notes

No deploy or runtime restart was performed. Runtime default remains `legacy_gate` unless `[authority].mode` is explicitly set in scanner config.
