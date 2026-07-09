# AgentTodo MAG-030 Agent Spine Design Report

Date: 2026-05-07
Role: PM / PA local design checkpoint
Status: DONE

## Scope

Continued AgentTodo after M2 completion and closed MAG-030, the first M3 Agent
Decision Spine Shadow item.

MAG-030 deliverable:

- RFC for `rust/openclaw_engine/src/agent_spine/`.
- Concrete module files.
- Rust interfaces.
- Store tables and idempotency keys.
- Feature flags and rollout modes.
- Handoff seams for MAG-031..035.

## Result

Created:

- `docs/architecture/multi_agent_rework_2026-05-05/2026-05-07--mag030_agent_spine_rust_module_design.md`

Updated:

- `docs/architecture/multi_agent_rework_2026-05-05/AgentTodo.md`
- `TODO.md`
- `.codex/MEMORY.md`
- `docs/CCAgentWorkSpace/PM/memory.md`

The RFC keeps M3 shadow-first:

- `disabled` remains default.
- `shadow` writes lineage rows without changing behavior.
- `canary` / `primary` are reserved for later acceptance.
- Store failures are warn-only in shadow and fail-closed only in primary for
  new or exposure-increasing orders.

## Authority Check

Fact:

- M2 has already converted scanner ranking into advisory evidence and preserved
  no-auto-close behavior.
- M3 now starts with typed Agent Decision Spine design.

Inference:

- MAG-031 should only publish `StrategySignal` shadow objects.
- MAG-032 must land durable store and idempotency tables before Python agents
  can publish the rest of the typed chain.

Assumption:

- No primary spine enforcement is allowed before MAG-034 idempotency audit and
  MAG-035 shadow integration proof.

## Dispatch Notes

Subagents were not spawned because this turn did not include an explicit user
request for delegated agent execution, and MAG-030 is a design RFC rather than
business-code implementation. The repo-chain roles are represented as:

- PM: triage and final integration.
- PA: local RFC design.
- E2/E4: deferred to MAG-034/MAG-035, where the M3 audit and regression gates
  are explicit AgentTodo items.

## Verification

Docs-only checkpoint:

- No Rust/Python runtime code changed.
- No rebuild, restart, deploy, database write, or feature-flag flip performed.
- Acceptance criteria checked against MAG-030 text: module files, interfaces,
  stores, and feature flags are all present.

## Next AgentTodo Item

Next: MAG-031 `StrategySignal` adapter for Rust strategies.

Boundaries for MAG-031:

- Shadow-only.
- Persist existing strategy outputs as `StrategySignal`.
- Do not execute through spine.
- Do not alter legacy dispatch behavior.
