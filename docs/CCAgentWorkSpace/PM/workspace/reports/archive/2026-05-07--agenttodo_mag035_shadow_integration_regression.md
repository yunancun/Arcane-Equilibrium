# AgentTodo MAG-035 Shadow Integration Regression Report

Date: 2026-05-07
Role: PM / E4 local regression checkpoint
Status: DONE

## Scope

Closed AgentTodo M3 by adding a Rust shadow integration regression for the
Agent Spine chain.

## Result

Added regression:

- `shadow_spine_chain_is_complete_while_legacy_signal_msg_stays_unchanged`

The test starts from the same legacy Rust open intent, builds a typed
`StrategySignal`, preserves the legacy `TradingMsg::Signal` serialized shape,
and then constructs the shadow spine chain:

- `StrategySignal`
- `StrategistDecision`
- `GuardianVerdict`
- `ExecutionPlan`
- `ExecutionReport`
- execution idempotency reservation

It asserts the complete edge sequence:

- `signal_for`
- `reviewed_by`
- `planned_by`
- `executed_by`

It also asserts the legacy signal serialization is unchanged before and after
building the shadow chain.

## Boundary

No runtime deploy, rebuild, restart, DB migration apply, DB write, feature-flag
flip, live auth mutation, trading mode change, or risk/strategy config change
was performed.

This is a regression test only. The Agent Spine writer remains default-disabled
and runtime startup remains unwired.

## Verification

Mac:

- `cargo fmt -p openclaw_engine --check` from `srv/rust`
- `cargo test -p openclaw_engine agent_spine --features replay_isolated` from `srv/rust`
  - 6 passed
- `git diff --check`

Linux `trade-core` temp worktree `/tmp/tradebot_mag035_shadow_regression`:

- `PATH=$HOME/.cargo/bin:$PATH cargo fmt -p openclaw_engine --check` from `srv/rust`
- `PATH=$HOME/.cargo/bin:$PATH cargo test -p openclaw_engine agent_spine --features replay_isolated` from `srv/rust`
  - 6 passed
- `git diff --check --cached`

## Next AgentTodo Item

M3 Agent Decision Spine Shadow is closed. Next: M4 MAG-040 Strategist V2
strategy matching model.
