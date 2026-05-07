# AgentTodo MAG-032 Durable Spine Store Report

Date: 2026-05-07
Role: PM / E1 local implementation checkpoint
Status: DONE

## Scope

Continued AgentTodo M3 after MAG-031 and implemented MAG-032:

- Add durable `agent_spine` store schema for typed lineage objects.
- Add Rust envelopes/store messages for StrategistDecision, GuardianVerdict,
  ExecutionPlan, and ExecutionReport.
- Add a fail-soft DB writer surface, without wiring it into runtime startup.
- Prove the chain shape can model signal -> decision -> verdict -> plan.

## Result

Added:

- `sql/migrations/V064__agent_spine_decision_store.sql`
- `rust/openclaw_engine/src/agent_spine/events.rs`
- `rust/openclaw_engine/src/agent_spine/store.rs`
- `rust/openclaw_engine/src/database/agent_spine_writer.rs`
- `tests/migrations/test_v064_agent_spine_decision_store.py`

Changed:

- `rust/openclaw_engine/src/agent_spine/contracts.rs`
- `rust/openclaw_engine/src/agent_spine/mod.rs`
- `rust/openclaw_engine/src/agent_spine/tests.rs`
- `rust/openclaw_engine/src/database/mod.rs`

V064 creates `agent.decision_objects`, `agent.decision_edges`,
`agent.decision_state_changes`, and `agent.execution_idempotency_keys`, with
idempotency constraints and indexes for chain queries. Rust now has typed
object envelopes, edge/state transition messages, execution idempotency
reservations, a channel-backed store, and a DB writer matching the existing
fail-soft writer pattern.

## Boundary

No runtime deploy, rebuild, restart, DB migration apply, DB write, feature-flag
flip, live auth mutation, trading mode change, or risk/strategy config change
was performed.

The writer is source-only in MAG-032. Startup/runtime integration remains a
later AgentTodo item.

## Verification

Mac:

- `cargo fmt -p openclaw_engine --check`
- `cargo test -p openclaw_engine agent_spine --features replay_isolated`
  - 5 passed
- `cargo test -p openclaw_engine tick_pipeline::tests::fast_track_reduce --features replay_isolated`
  - 18 passed
- `cargo test -p openclaw_engine database::migrations::tests::load_migrations_real_srv_tree --features replay_isolated`
  - 1 passed
- `python3 -m pytest tests/migrations/test_v064_agent_spine_decision_store.py -q`
  - 4 passed
- `git diff --check`

Linux `trade-core` temp worktree `/tmp/tradebot_mag032_agent_spine`:

- `cargo fmt -p openclaw_engine --check`
- `cargo test -p openclaw_engine agent_spine --features replay_isolated`
  - 5 passed
- `cargo test -p openclaw_engine tick_pipeline::tests::fast_track_reduce --features replay_isolated`
  - 18 passed
- `cargo test -p openclaw_engine database::migrations::tests::load_migrations_real_srv_tree --features replay_isolated`
  - 1 passed
- `python3 -m pytest tests/migrations/test_v064_agent_spine_decision_store.py -q`
  - 4 passed
- `git diff --check`

Existing warnings from unrelated modules were observed and did not block.

## Next AgentTodo Item

Next: MAG-033 Python `agent_spine_client.py` for Strategist / Guardian /
Analyst typed object interaction.
