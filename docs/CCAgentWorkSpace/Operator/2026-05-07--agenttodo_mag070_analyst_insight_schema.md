# Operator Handoff: AgentTodo MAG-070 AnalystInsight Schema

Date: 2026-05-07
Status: DONE

## What changed

- Defined AnalystInsight L1/L2/L3 schema boundaries.
- Python contracts now carry analyst tier, tier-scoped insight type,
  fact/inference/hypothesis level, bounded confidence, recommendation, and
  severity.
- AgentSpine analyzed_by edges now include analyst tier/type/level metadata.

## Verification

- Mac targeted py_compile, pytest 33/0, and diff check passed.
- Linux `trade-core` temp-worktree targeted py_compile, pytest 33/0, and diff
  check passed.

## Boundary

- No runtime Analyst emission wiring, Strategist/Guardian behavior change,
  cloud call, rebuild, restart, deploy, DB write, live auth, runtime flag, or
  trading authority change.

## AgentTodo position

- M7 has started.
- MAG-070 is closed.
- Next AgentTodo item: MAG-071 Persist AnalystInsight evidence links.
