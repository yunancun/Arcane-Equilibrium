# AgentTodo MAG-070 AnalystInsight Schema

Date: 2026-05-07
Owner: PM-local execution
Status: DONE

## Scope

Define the AnalystInsight L1/L2/L3 schema boundary for the Analyst Learning
Loop. This was a contract/schema task only.

## Implementation

- Added the schema note:
  `docs/architecture/multi_agent_rework_2026-05-05/2026-05-07--mag070_analyst_insight_l1_l2_l3_schema.md`.
- Extended Python `AnalystInsight` with:
  - `analyst_tier`: `l1`, `l2`, or `l3`.
  - tier-scoped `insight_type`.
  - `insight_level`: `fact`, `inference`, or `hypothesis`.
  - bounded `confidence`.
  - optional `recommendation` and `severity`.
- Added `AnalystInsightL1`, `AnalystInsightL2`, and `AnalystInsightL3`
  contract subclasses.
- Updated `AgentSpineClient.publish_analyst_insight()` so analyzed_by edge
  details include analyst tier, type, level, confidence, and severity.
- Added tests that build valid L1/L2/L3 insights and reject invalid tier/type
  or confidence boundaries.

## Verification

- Mac:
  - `python3 -m py_compile ... agent_contracts.py agent_spine_client.py strategist_decision_v2.py ...`
  - `python3 -m pytest ... test_agent_spine_client.py test_strategist_decision_v2.py test_strategist_v2_replay_not_scanner_sorting.py -q`
  - `git diff --check`
- Linux `trade-core` temp worktree:
  - same py_compile
  - same pytest set
  - same diff check

Focused result: 33 Python tests pass.

## Boundary

- No runtime Analyst emission wiring.
- No Strategist/Guardian behavior change.
- No cloud call.
- No runtime submit path.
- No Rust contract change.
- No rebuild, restart, deploy, DB write, live auth, runtime flag, or trading
  authority change.

## Next

M7 continues with MAG-071 Persist AnalystInsight evidence links.
