# AgentTodo MAG-031 StrategySignal Adapter Report

Date: 2026-05-07
Role: PM / E1 local implementation checkpoint
Status: DONE

## Scope

Continued AgentTodo M3 after MAG-030 and implemented MAG-031:

- Add Rust `agent_spine` StrategySignal contracts.
- Add a strategy-output adapter for existing Rust strategy open intents.
- Preserve the existing legacy `trading.signals` persistence shape until
  MAG-032 lands the durable spine store.
- Do not change strategy dispatch, Guardian, Decision Lease, order dispatch,
  scanner authority, or runtime feature flags.

## Result

Added:

- `rust/openclaw_engine/src/agent_spine/mod.rs`
- `rust/openclaw_engine/src/agent_spine/config.rs`
- `rust/openclaw_engine/src/agent_spine/contracts.rs`
- `rust/openclaw_engine/src/agent_spine/signal_adapter.rs`
- `rust/openclaw_engine/src/agent_spine/tests.rs`

Changed:

- `rust/openclaw_engine/src/lib.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`

`persist_strategy_signal()` now builds a typed
`agent_spine::contracts::StrategySignal` from the existing `OrderIntent`, then
downgrades it to `TradingMsg::Signal` for the current DB writer. This keeps the
current row shape and timing intact while making the hot path use the formal M3
contract first.

## Boundary

No runtime deploy, rebuild, restart, DB migration, DB write, feature-flag flip,
live auth mutation, trading mode change, or risk/strategy config change was
performed.

MAG-031 does not add the durable `agent.decision_objects` store. That remains
MAG-032.

## Verification

Mac:

- `cargo fmt -p openclaw_engine --check`
- `cargo test -p openclaw_engine agent_spine --features replay_isolated`
  - 3 passed
- `cargo test -p openclaw_engine tick_pipeline::tests::fast_track_reduce --features replay_isolated`
  - 18 passed
- `git diff --check`

Linux `trade-core` temp worktree `/tmp/tradebot_mag031_agent_spine`:

- `cargo fmt -p openclaw_engine --check`
- `cargo test -p openclaw_engine agent_spine --features replay_isolated`
  - 3 passed
- `cargo test -p openclaw_engine tick_pipeline::tests::fast_track_reduce --features replay_isolated`
  - 18 passed

Existing warnings from unrelated modules were observed and did not block.

## Next AgentTodo Item

Next: MAG-032 `agent_spine` durable store for StrategistDecision,
GuardianVerdict, ExecutionPlan, and ExecutionReport lineage.
